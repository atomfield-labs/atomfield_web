"""
Run jobs on a Slurm cluster from its login node.

The agent hands each job to Slurm (``sbatch``) instead of running it,
so it is no longer the job's parent and nobody tells it when the job
ends. One watcher asks Slurm instead: a single ``squeue`` for all of
the user's jobs every ``poll_seconds`` (schedulers are shared; one
call per job would hammer them). A job that leaves the queue has
ended; its exit code comes from ``sacct``, or, where accounting is
off, from the ``.af_exit`` file its batch script writes.

A failed ``squeue`` (timeout, controller busy) never means "ended":
the watcher simply asks again next time.
"""

import asyncio
import getpass
import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from agent.runner import GRACE_SECONDS, Command
from app.catalog.models import Resources

logger = logging.getLogger("agent.slurm")
EXIT_FILE = ".af_exit"
LOGIN_SHELL = "#!/bin/bash -l"
SCRIPT_NAME = "job.sbatch"
# Slurm states of a job that has begun running.
RUNNING_STATES = {"RUNNING", "COMPLETING", "STOPPED", "SUSPENDED"}
# sacct states of a job that is over.
ENDED_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "TIMEOUT",
}
TIMEOUT_STATE = "TIMEOUT"
# Threads per process: the job's CPUs for threaded tasks (no stealing
# cores from neighbours on a shared node), one for MPI processes.
OMP_THREADS = "$SLURM_CPUS_PER_TASK"
OMP_THREADS_MPI = "1"
# A job gone from squeue with no exit code anywhere: wait a few polls
# (accounting can lag), then give up and call it failed.
UNKNOWN_EXIT_POLLS = 3
UNKNOWN_EXIT_CODE = 1


class SlurmCommandError(RuntimeError):
    """
    A Slurm command failed (e.g. ``sbatch`` refused a job).
    """


@dataclass(frozen=True, slots=True)
class SlurmSettings:
    """
    How this cluster wants jobs submitted.

    :param options: Extra ``#SBATCH`` options, e.g. ``--account=chem1``.
    :type options: list[str]
    :param setup_lines: Shell lines run before the job, e.g.
        ``module load anaconda``.
    :type setup_lines: list[str]
    :param poll_seconds: Time between ``squeue`` calls.
    :type poll_seconds: float
    :param command_timeout: Longest wait for one Slurm command.
    :type command_timeout: float
    :param environment: Environment for Slurm commands (None: the
        agent's own). Tests put fake commands on ``PATH`` here.
    :type environment: dict[str, str] | None
    """

    options: list[str] = field(default_factory=list)
    setup_lines: list[str] = field(default_factory=list)
    poll_seconds: float = 15.0
    command_timeout: float = 60.0
    environment: dict[str, str] | None = None


def parallel_directives(resources: Resources) -> list[str]:
    """
    Ask Slurm for the right kind of parallelism.

    An MPI task (Quantum ESPRESSO) runs ``cpus`` processes, kept on one
    node so they talk quickly; any other task (xTB) runs one process
    with ``cpus`` threads.

    :param resources: The task's resources from the catalog.
    :type resources: Resources
    :return: ``#SBATCH`` options.
    :rtype: list[str]
    """
    if resources.mpi:
        return [f"--ntasks={resources.cpus}", "--cpus-per-task=1", "--nodes=1"]
    return ["--ntasks=1", f"--cpus-per-task={resources.cpus}"]


def sbatch_directives(command: Command, settings: SlurmSettings) -> list[str]:
    """
    One job's ``#SBATCH`` options: its name, folder and log, its
    resources from the task catalog (``--time`` lets Slurm itself stop
    the job at its limit), then the cluster's own options.

    :param command: What to run.
    :type command: Command
    :param settings: Cluster-specific options.
    :type settings: SlurmSettings
    :return: The options.
    :rtype: list[str]
    """
    resources = command.resources
    return [
        f"--job-name={command.name}",
        f"--chdir={command.workspace}",
        f"--output={command.log_path}",
        *parallel_directives(resources),
        f"--mem={resources.memory_mb}M",
        f"--time={resources.walltime_minutes}",
        *settings.options,
    ]


def script_header(command: Command, settings: SlurmSettings) -> list[str]:
    """
    The start of a batch script: a login shell (on most clusters
    ``module`` exists only there, and the setup lines usually load
    modules), the ``#SBATCH`` options, then threads per process, set
    before the setup lines so a module can still change it.

    :param command: What to run.
    :type command: Command
    :param settings: Cluster-specific options.
    :type settings: SlurmSettings
    :return: Script lines.
    :rtype: list[str]
    """
    directives = sbatch_directives(command, settings)
    threads = OMP_THREADS_MPI if command.resources.mpi else OMP_THREADS
    return [
        LOGIN_SHELL,
        *(f"#SBATCH {directive}" for directive in directives),
        f"export OMP_NUM_THREADS={threads}",
    ]


def batch_script(command: Command, settings: SlurmSettings) -> str:
    """
    Write the batch script for one job. The command's exit code is
    saved to ``.af_exit`` for clusters without accounting.

    :param command: What to run.
    :type command: Command
    :param settings: Cluster-specific options and setup lines.
    :type settings: SlurmSettings
    :return: Script text.
    :rtype: str
    """
    exports = [
        f"export {name}={shlex.quote(value)}"
        for name, value in command.environment.items()
    ]
    lines = [
        *script_header(command, settings),
        *settings.setup_lines,
        *exports,
        shlex.join(command.argv),
        "status=$?",
        f"echo $status > {EXIT_FILE}",
        "exit $status",
    ]
    return "\n".join(lines) + "\n"


async def run_slurm(
    args: list[str],
    settings: SlurmSettings,
) -> tuple[int, str, str]:
    """
    Run one Slurm command with a time limit.

    :param args: Command and arguments, e.g. ``["squeue", "-h"]``.
    :type args: list[str]
    :param settings: Holds the timeout and environment.
    :type settings: SlurmSettings
    :return: Exit code, stdout and stderr.
    :rtype: tuple[int, str, str]
    :raises TimeoutError: If the command takes too long.
    :raises OSError: If the command cannot be started (not installed).
    """
    process = await start_slurm(args, settings)
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), settings.command_timeout
        )
    except (TimeoutError, asyncio.CancelledError):
        # Never leave a stray Slurm command behind (a hung squeue, or
        # one interrupted by the agent shutting down).
        process.kill()
        await process.wait()
        raise
    return process.returncode, stdout.decode(), stderr.decode()


async def start_slurm(
    args: list[str], settings: SlurmSettings
) -> asyncio.subprocess.Process:
    """
    Start one Slurm command, its output captured.

    :param args: Command and arguments.
    :type args: list[str]
    :param settings: Holds the environment.
    :type settings: SlurmSettings
    :return: The running command.
    :rtype: asyncio.subprocess.Process
    :raises OSError: If the command cannot be started (not installed).
    """
    return await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=settings.environment,
    )


def parse_queue(text: str) -> dict[str, str]:
    """
    Read ``squeue -o '%i|%T'`` output.

    :param text: One ``<job id>|<state>`` per line.
    :type text: str
    :return: Job id -> state.
    :rtype: dict[str, str]
    """
    states = {}
    for line in text.splitlines():
        job_id, _, state = line.strip().partition("|")
        if job_id and state:
            states[job_id] = state
    return states


def parse_accounting(text: str, job_id: str) -> tuple[str, int] | None:
    """
    Read a job's final state and exit code from ``sacct -P`` output.

    :param text: ``<job id>|<state>|<exit>:<signal>`` lines (steps too).
    :type text: str
    :param job_id: The job (its own line, not ``<id>.batch``).
    :type job_id: str
    :return: State and exit code, or None if the job is not over yet.
    :rtype: tuple[str, int] | None
    """
    for line in text.splitlines():
        fields = line.strip().split("|")
        if len(fields) < 3 or fields[0] != job_id:
            continue
        state = fields[1].split()[0]  # "CANCELLED by 1234" -> CANCELLED
        if state not in ENDED_STATES:
            return None
        exit_code, _, signal_text = fields[2].partition(":")
        code, signal_number = int(exit_code or 0), int(signal_text or 0)
        if state != "COMPLETED" and code == 0:
            # Killed by a signal: report it the way a shell would.
            code = 128 + signal_number if signal_number else 1
        return state, code
    return None


class SlurmExecution:
    """
    One Slurm job, as the watcher last saw it.
    """

    def __init__(self, job_id: str, workspace: Path, runner: "SlurmRunner"):
        """
        :param job_id: Slurm's job id.
        :type job_id: str
        :param workspace: The job's folder (for ``.af_exit``).
        :type workspace: Path
        :param runner: Runner that watches and cancels it.
        :type runner: SlurmRunner
        """
        self.handle = job_id
        self.workspace = workspace
        self.runner = runner
        self.started = False
        self.timed_out = False
        self.state = "PENDING"
        self.exit_code: int | None = None
        self.missing_polls = 0
        self.ended = asyncio.Event()

    def update(self, state: str) -> None:
        """
        Note the job's state in the queue.

        :param state: Slurm state, e.g. PENDING or RUNNING.
        :type state: str
        """
        self.state = state
        self.missing_polls = 0
        if state in RUNNING_STATES:
            self.started = True

    def finish(self, state: str, exit_code: int) -> None:
        """
        Record how the job ended and wake whoever waits on it.

        :param state: Final Slurm state (or ``UNKNOWN``).
        :type state: str
        :param exit_code: Exit code.
        :type exit_code: int
        """
        self.state = state
        self.exit_code = exit_code
        self.timed_out = state == TIMEOUT_STATE
        self.started = True
        self.ended.set()

    async def wait(self) -> int:
        """
        Wait until the watcher sees the job end.

        :return: Exit code.
        :rtype: int
        """
        await self.ended.wait()
        return self.exit_code

    async def terminate(self, grace_seconds: float = GRACE_SECONDS) -> None:
        """
        Cancel the job (Slurm sends SIGTERM, then SIGKILL after its own
        grace time) and wait for the watcher to see it end.

        :param grace_seconds: Extra time to wait, on top of one poll.
        :type grace_seconds: float
        """
        await self.runner.cancel(self.handle)
        limit = grace_seconds + 2 * self.runner.settings.poll_seconds
        try:
            await asyncio.wait_for(self.ended.wait(), limit)
        except TimeoutError:
            logger.warning(
                "Slurm job %s did not end after scancel", self.handle
            )


class SlurmRunner:
    """
    Submits jobs to Slurm and watches them with one shared poll.
    """

    scheduled = True

    def __init__(self, settings: SlurmSettings) -> None:
        """
        :param settings: Cluster-specific options.
        :type settings: SlurmSettings
        """
        self.settings = settings
        self.watching: dict[str, SlurmExecution] = {}
        self.watcher: asyncio.Task | None = None
        self.poke = asyncio.Event()

    async def start(self, command: Command) -> SlurmExecution:
        """
        Write the job's batch script into its folder and submit it.

        :param command: What to run.
        :type command: Command
        :return: The queued job.
        :rtype: SlurmExecution
        :raises SlurmCommandError: If ``sbatch`` refuses the job (bad
            account or partition, too many resources...).
        """
        script = command.workspace / SCRIPT_NAME
        script.write_text(batch_script(command, self.settings))
        args = ["sbatch", "--parsable", str(script)]
        code, stdout, stderr = await run_slurm(args, self.settings)
        if code != 0:
            raise SlurmCommandError(f"sbatch refused the job: {stderr.strip()}")
        # --parsable prints "<id>" or "<id>;<cluster>".
        job_id = stdout.strip().split(";")[0]
        return self.watch(SlurmExecution(job_id, command.workspace, self))

    async def adopt(self, handle: str, workspace: Path) -> SlurmExecution:
        """
        Take over a job a previous agent submitted: Slurm kept it
        running (or finished it) while the agent was away.

        :param handle: Slurm job id.
        :type handle: str
        :param workspace: The job's folder.
        :type workspace: Path
        :return: The job, watched again.
        :rtype: SlurmExecution
        """
        return self.watch(SlurmExecution(handle, workspace, self))

    def watch(self, execution: SlurmExecution) -> SlurmExecution:
        """
        Add a job to the shared poll, starting the poll if needed.

        :param execution: The job.
        :type execution: SlurmExecution
        :return: The same job.
        :rtype: SlurmExecution
        """
        self.watching[execution.handle] = execution
        if self.watcher is None or self.watcher.done():
            self.watcher = asyncio.create_task(self.poll_forever())
        self.poke.set()
        return execution

    async def close(self) -> None:
        """
        Stop watching (the agent is shutting down). The jobs keep
        running in Slurm; the next agent takes them over.
        """
        if self.watcher is not None:
            self.watcher.cancel()
            await asyncio.gather(self.watcher, return_exceptions=True)

    async def cancel(self, job_id: str) -> None:
        """
        Ask Slurm to cancel a job, then look at the queue soon.

        :param job_id: Slurm job id.
        :type job_id: str
        """
        code, _, stderr = await run_slurm(["scancel", job_id], self.settings)
        if code != 0:
            logger.warning("scancel %s failed: %s", job_id, stderr.strip())
        self.poke.set()

    async def poll_forever(self) -> None:
        """
        Poll while there are jobs to watch; sleep between polls unless
        poked (a new job, a cancel).
        """
        while self.watching:
            self.poke.clear()
            await self.poll_once()
            try:
                await asyncio.wait_for(
                    self.poke.wait(), self.settings.poll_seconds
                )
            except TimeoutError:
                pass

    async def poll_once(self) -> None:
        """
        One ``squeue`` for every job; settle the ones that left it.
        """
        states = await self.queue_states()
        if states is None:
            return
        for job_id, execution in list(self.watching.items()):
            if job_id in states:
                execution.update(states[job_id])
            else:
                await self.settle(execution)

    async def queue_states(self) -> dict[str, str] | None:
        """
        This user's jobs in the queue.

        :return: Job id -> state, or None if Slurm could not be asked
            (then nothing may be concluded).
        :rtype: dict[str, str] | None
        """
        # --user rather than --me: --me needs Slurm 20.11 or newer.
        user = f"--user={getpass.getuser()}"
        args = ["squeue", "--noheader", user, "--format=%i|%T"]
        try:
            code, stdout, stderr = await run_slurm(args, self.settings)
        except (TimeoutError, OSError) as error:
            logger.warning("squeue failed (%s); asking again later", error)
            return None
        if code != 0:
            logger.warning("squeue failed: %s", stderr.strip())
            return None
        return parse_queue(stdout)

    async def settle(self, execution: SlurmExecution) -> None:
        """
        A job left the queue: find out how it ended.

        :param execution: The job.
        :type execution: SlurmExecution
        """
        outcome = await self.accounting(execution.handle)
        if outcome is None:
            outcome = read_exit_file(execution.workspace)
        if outcome is None:
            execution.missing_polls += 1
            if execution.missing_polls < UNKNOWN_EXIT_POLLS:
                return
            outcome = ("UNKNOWN", UNKNOWN_EXIT_CODE)
        execution.finish(*outcome)
        self.watching.pop(execution.handle, None)

    async def accounting(self, job_id: str) -> tuple[str, int] | None:
        """
        A finished job's state and exit code from ``sacct``.

        :param job_id: Slurm job id.
        :type job_id: str
        :return: State and code; None if accounting is off, slow, or
            says the job is not over.
        :rtype: tuple[str, int] | None
        """
        args = [
            "sacct",
            "--noheader",
            "--parsable2",
            f"--jobs={job_id}",
            "--format=JobID,State,ExitCode",
        ]
        try:
            code, stdout, _ = await run_slurm(args, self.settings)
        except (TimeoutError, OSError):
            return None
        return parse_accounting(stdout, job_id) if code == 0 else None


def read_exit_file(workspace: Path) -> tuple[str, int] | None:
    """
    The exit code the batch script saved, for clusters without
    accounting.

    :param workspace: The job's folder.
    :type workspace: Path
    :return: ``("COMPLETED" or "FAILED", code)``, or None if absent.
    :rtype: tuple[str, int] | None
    """
    path = workspace / EXIT_FILE
    try:
        code = int(path.read_text().strip())
    except (OSError, ValueError):
        return None
    return ("COMPLETED" if code == 0 else "FAILED"), code
