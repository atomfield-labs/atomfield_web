"""
The Slurm runner, against fake Slurm commands that run real batch
scripts: submit, watch with one shared poll, read exit codes with and
without accounting, cancel, survive a failing ``squeue``, adopt.
"""

import asyncio
import dataclasses
import sys
from pathlib import Path

import pytest

from agent.runner import Command
from agent.slurm import (
    SlurmCommandError,
    SlurmRunner,
    SlurmSettings,
    batch_script,
    parse_accounting,
    parse_queue,
)
from agent.workspace import job_environment
from app.catalog.argv import Invocation, build_argv
from app.catalog.catalog import Catalog
from tests.fake_pack import SLOW_CHARGE, WATER_XYZ, install_fake_pack
from tests.fake_slurm import install_fake_slurm

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
CATALOG = Catalog.from_path(FIXTURE)
TASK = CATALOG.get("toy_opt")
WAIT_SECONDS = 20


def make_command(root: Path, charge: int = 1) -> Command:
    """
    A ``toy_opt`` command on water, in ``root/runs/r1/opt``.

    :param root: Empty folder for the pack and the job.
    :type root: Path
    :param charge: Charge; SLOW_CHARGE sleeps, negative fails.
    :type charge: int
    :return: Command ready to submit.
    :rtype: Command
    """
    pack = install_fake_pack(root)
    workspace = root / "runs" / "r1" / "opt"
    workspace.mkdir(parents=True)
    (workspace / "water.xyz").write_text(WATER_XYZ)
    values = CATALOG.validate_values("toy_opt", {"charge": charge})
    invocation = Invocation(
        values=values,
        inputs={"structure": ["water.xyz"]},
        job_name="toy_opt",
        cpus=TASK.resources.cpus,
    )
    return Command(
        argv=build_argv(TASK, invocation, sys.executable),
        workspace=workspace,
        log_path=workspace / "execution.log",
        environment=job_environment(pack),
        name="af-opt",
        resources=TASK.resources,
    )


def fake_cluster(root: Path, **switches: str) -> SlurmRunner:
    """
    A Slurm runner on fake commands, polling fast.

    :param root: Empty folder for the fake commands' state.
    :type root: Path
    :param switches: ``FAKE_SLURM_*`` settings.
    :type switches: str
    :return: Runner.
    :rtype: SlurmRunner
    """
    environment = {**install_fake_slurm(root / "slurm"), **switches}
    settings = SlurmSettings(poll_seconds=0.1, environment=environment)
    return SlurmRunner(settings)


def run(coroutine):
    """
    Run a scenario, failing if it hangs.

    :param coroutine: The scenario.
    :type coroutine: Coroutine
    :return: Its result.
    :rtype: Any
    """

    async def bounded():
        async with asyncio.timeout(WAIT_SECONDS):
            return await coroutine

    return asyncio.run(bounded())


def test_the_batch_script_asks_for_the_tasks_resources(tmp_path: Path):
    """
    Resources come from the catalog, the time limit is Slurm's to
    enforce, cluster options and setup lines are included, values are
    shell-quoted, and the exit code is kept for clusters without
    accounting.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path)
    settings = SlurmSettings(
        options=["--account=chem 1", "--partition=short"],
        setup_lines=["module load anaconda"],
    )
    script = batch_script(command, settings)

    resources = TASK.resources
    assert script.startswith("#!/bin/bash -l\n")
    for directive in (
        f"--cpus-per-task={resources.cpus}",
        f"--mem={resources.memory_mb}M",
        f"--time={resources.walltime_minutes}",
        f"--chdir={command.workspace}",
        "--job-name=af-opt",
        "--partition=short",
    ):
        assert f"#SBATCH {directive}\n" in script
    setup = script.index("module load anaconda")
    assert setup < script.index("export PYTHONUNBUFFERED")
    assert "export PYTHONUNBUFFERED=1\n" in script
    assert script.rstrip().endswith("echo $status > .af_exit\nexit $status")


@pytest.mark.parametrize(
    ("mpi", "expected", "threads"),
    [
        (False, ["--ntasks=1", "--cpus-per-task=4"], "$SLURM_CPUS_PER_TASK"),
        (True, ["--ntasks=4", "--cpus-per-task=1", "--nodes=1"], "1"),
    ],
    ids=["threads", "mpi"],
)
def test_threads_and_mpi_processes_are_requested_differently(
    tmp_path: Path, mpi: bool, expected: list[str], threads: str
):
    """
    A threaded task gets one process with its CPUs; an MPI task (QE)
    gets that many single-threaded processes on one node.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param mpi: Whether the task runs MPI processes.
    :type mpi: bool
    :param expected: ``#SBATCH`` options it must get.
    :type expected: list[str]
    :param threads: Expected ``OMP_NUM_THREADS``.
    :type threads: str
    """
    command = make_command(tmp_path)
    resources = command.resources.model_copy(update={"cpus": 4, "mpi": mpi})
    command = dataclasses.replace(command, resources=resources)
    script = batch_script(command, SlurmSettings(setup_lines=["module x"]))

    for directive in expected:
        assert f"#SBATCH {directive}\n" in script
    assert f"export OMP_NUM_THREADS={threads}\n" in script
    assert script.index("OMP_NUM_THREADS") < script.index("module x")


def test_a_job_runs_through_slurm_to_its_exit_code(tmp_path: Path):
    """
    Submitted, watched until it leaves the queue, exit code from
    accounting; the outputs land in the job's folder.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path)
    runner = fake_cluster(tmp_path)

    async def scenario():
        execution = await runner.start(command)
        return execution, await execution.wait()

    execution, code = run(scenario())
    assert (code, execution.handle, execution.started) == (0, "1000", True)
    assert (command.workspace / "toy_opt_optimized.xyz").exists()
    assert (command.workspace / "job.sbatch").exists()


@pytest.mark.parametrize("accounting", ["on", "off"])
def test_a_failed_job_keeps_its_exit_code(tmp_path: Path, accounting: str):
    """
    The script's own exit code comes back, from ``sacct`` or, where
    accounting is off, from ``.af_exit``.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param accounting: Whether ``sacct`` works.
    :type accounting: str
    """
    switches = {"FAKE_SLURM_NO_ACCOUNTING": "1"} if accounting == "off" else {}
    command = make_command(tmp_path, charge=-1)
    runner = fake_cluster(tmp_path, **switches)

    async def scenario():
        return await (await runner.start(command)).wait()

    assert run(scenario()) == 3


def test_a_queued_job_is_not_started_until_slurm_runs_it(tmp_path: Path):
    """
    While Slurm keeps the job waiting it is not started; then it is.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path)
    runner = fake_cluster(tmp_path, FAKE_SLURM_PENDING_SECONDS="1")

    async def scenario():
        execution = await runner.start(command)
        await asyncio.sleep(0.4)
        waiting = execution.started
        code = await execution.wait()
        return waiting, execution.started, code

    assert run(scenario()) == (False, True, 0)


def test_cancelling_stops_the_job(tmp_path: Path):
    """
    ``terminate`` cancels through ``scancel``; the job ends cancelled.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path, charge=SLOW_CHARGE)
    runner = fake_cluster(tmp_path)

    async def scenario():
        execution = await runner.start(command)
        while not execution.started:
            await asyncio.sleep(0.05)
        await execution.terminate(grace_seconds=1)
        return execution.state, await execution.wait()

    state, code = run(scenario())
    assert state == "CANCELLED"
    assert code == 143


def test_a_failing_squeue_never_ends_a_job(tmp_path: Path):
    """
    While ``squeue`` fails, nothing is concluded, even though the job
    has long finished; once it answers again, the job settles.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    outage = tmp_path / "squeue_down"
    outage.touch()
    command = make_command(tmp_path)
    runner = fake_cluster(tmp_path, FAKE_SLURM_SQUEUE_DOWN=str(outage))

    async def scenario():
        execution = await runner.start(command)
        await asyncio.sleep(1.0)
        ended_during_outage = execution.ended.is_set()
        outage.unlink()
        return ended_during_outage, await execution.wait()

    assert run(scenario()) == (False, 0)


def test_a_refused_submission_says_why(tmp_path: Path):
    """
    ``sbatch``'s own message (bad account, too much memory...) reaches
    the job's failure report.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path)
    runner = fake_cluster(tmp_path, FAKE_SLURM_REJECT="Invalid account")

    with pytest.raises(SlurmCommandError, match="Invalid account"):
        run(runner.start(command))


def test_a_restarted_agent_adopts_a_job_slurm_kept_running(tmp_path: Path):
    """
    A new runner (as after an agent restart) takes the job over by its
    Slurm id and watches it to the end.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    command = make_command(tmp_path)
    first = fake_cluster(tmp_path, FAKE_SLURM_PENDING_SECONDS="0.5")

    async def scenario():
        submitted = await first.start(command)
        first.watching.clear()  # the old agent is gone
        second = SlurmRunner(first.settings)
        adopted = await second.adopt(submitted.handle, command.workspace)
        return await adopted.wait()

    assert run(scenario()) == 0


def test_slurm_output_is_read_carefully():
    """
    Queue lines and accounting lines, including job steps, signals and
    states that are not final yet.
    """
    assert parse_queue("12|RUNNING\n13|PENDING\n\n") == {
        "12": "RUNNING",
        "13": "PENDING",
    }
    accounting = "12|CANCELLED by 501|0:15\n12.batch|CANCELLED|0:15\n"
    assert parse_accounting(accounting, "12") == ("CANCELLED", 143)
    assert parse_accounting("12|TIMEOUT|0:0\n", "12") == ("TIMEOUT", 1)
    assert parse_accounting("12|FAILED|2:0\n", "12") == ("FAILED", 2)
    assert parse_accounting("12|COMPLETED|0:0\n", "12") == ("COMPLETED", 0)
    assert parse_accounting("12|RUNNING|0:0\n", "12") is None
    assert parse_accounting("12.batch|COMPLETED|0:0\n", "12") is None
