"""
The agent program, against a fake API client and real subprocesses:
reports, cancel, abandon, deadlines, crash recovery and fresh folders.
"""

import asyncio
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent.agent import Agent
from agent.config import AgentConfig
from agent.runner import ProcessRunner, group_is_alive
from agent.state import StateFile
from agent.workspace import prepare_workspace, session_folder
from app.agents.schemas import (
    CompletionRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
)
from app.catalog.catalog import Catalog
from tests.fake_pack import SLOW_CHARGE, create_session, install_fake_pack

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
CATALOG = Catalog.from_path(FIXTURE)
SESSION = {"pipeline_id": "session_1", "user_id": "user_1"}


def assign(deadline_seconds: float = 60.0, **values) -> JobAssignment:
    """
    An assignment of ``toy_opt`` on water.xyz, as the server would send.

    :param deadline_seconds: Seconds until the job's deadline.
    :type deadline_seconds: float
    :param values: toy_opt values; charge SLOW_CHARGE makes it sleep.
    :type values: Any
    :return: Assignment for attempt 1.
    :rtype: JobAssignment
    """
    values = CATALOG.validate_values("toy_opt", values)
    return JobAssignment(
        job_id=uuid.uuid4(),
        attempt=1,
        run_id=uuid.uuid4(),
        task=CATALOG.get("toy_opt"),
        parameters={**values, **SESSION},
        input_files={"structure": ["water.xyz"]},
        deadline_at=datetime.now(UTC) + timedelta(seconds=deadline_seconds),
    )


class FakeClient:
    """
    Stands in for the API: hands out the given assignments once, and
    answers heartbeats with the configured cancel/abandon sets.
    """

    def __init__(self, *assignments: JobAssignment) -> None:
        """
        Queue the assignments to hand out.

        :param assignments: Jobs to give the agent, in order.
        :type assignments: JobAssignment
        """
        self.pending = list(assignments)
        self.reports: dict[uuid.UUID, CompletionRequest] = {}
        self.cancel: set[uuid.UUID] = set()
        self.abandon: set[uuid.UUID] = set()

    async def claim(self, wait_seconds: float) -> JobAssignment | None:
        """
        Hand out the next assignment, or wait briefly and return None.

        :param wait_seconds: Ignored long-poll wait.
        :type wait_seconds: float
        :return: The next assignment, if any.
        :rtype: JobAssignment | None
        """
        if self.pending:
            return self.pending.pop(0)
        await asyncio.sleep(0.02)
        return None

    async def heartbeat(self, held: list[JobReference]) -> HeartbeatResponse:
        """
        Echo back which held attempts to cancel or abandon.

        :param held: Attempts the agent is running.
        :type held: list[JobReference]
        :return: Instructions.
        :rtype: HeartbeatResponse
        """
        return HeartbeatResponse(
            cancel=[ref for ref in held if ref.job_id in self.cancel],
            abandon=[ref for ref in held if ref.job_id in self.abandon],
        )

    async def complete(self, job_id, report: CompletionRequest) -> bool:
        """
        Record a report.

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Outcome.
        :type report: CompletionRequest
        :return: Always accepted.
        :rtype: bool
        """
        self.reports[job_id] = report
        return True


class RecordingState(StateFile):
    """
    A state file that also remembers every process group it saw.
    """

    def __init__(self, path: Path) -> None:
        """
        :param path: State file location.
        :type path: Path
        """
        super().__init__(path)
        self.groups: list[int] = []

    def record(self, job_id: str, attempt: int, process_group: int) -> None:
        """
        :param job_id: Job id.
        :type job_id: str
        :param attempt: Attempt number.
        :type attempt: int
        :param process_group: Its process group.
        :type process_group: int
        """
        self.groups.append(process_group)
        super().record(job_id, attempt, process_group)


def make_agent(tmp_path: Path, client: FakeClient) -> Agent:
    """
    An agent with fast timers, running the fake pack in tmp_path.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    :param client: Fake API client.
    :type client: FakeClient
    :return: Ready agent.
    :rtype: Agent
    """
    create_session(tmp_path / "jobs")
    config = AgentConfig(
        api_url="http://unused",
        token="unused",
        python_bin=sys.executable,
        pack_source_dir=install_fake_pack(tmp_path),
        artifacts_dir=tmp_path / "jobs",
        state_file=tmp_path / "state.json",
        heartbeat_seconds=0.05,
        claim_wait_seconds=0.05,
    )
    state = RecordingState(config.state_file)
    return Agent(config, client, ProcessRunner(), state)


def run_until(agent: Agent, condition, timeout: float = 20.0) -> None:
    """
    Run the agent until ``condition()`` holds, then stop it cleanly.

    :param agent: Agent to run.
    :type agent: Agent
    :param condition: Checked every 20 ms.
    :type condition: Callable[[], bool]
    :param timeout: Give up (and fail) after this many seconds.
    :type timeout: float
    """

    async def scenario():
        task = asyncio.create_task(agent.run())
        try:
            async with asyncio.timeout(timeout):
                while not condition():
                    await asyncio.sleep(0.02)
        finally:
            agent.request_stop()
            await task

    asyncio.run(scenario())


def test_a_finished_job_is_reported_with_its_files(tmp_path: Path):
    """
    Success carries the output file list; failure carries the log.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    good, bad = assign(charge=1), assign(charge=-1)
    client = FakeClient(good, bad)
    run_until(make_agent(tmp_path, client), lambda: len(client.reports) == 2)

    succeeded, failed = client.reports[good.job_id], client.reports[bad.job_id]
    assert succeeded.outcome == "succeeded"
    assert "toy_opt_optimized.xyz" in succeeded.output_data["artifacts"]
    assert failed.outcome == "failed"
    assert "toy_opt failed (code 3)" in failed.error_message
    assert "negative charge refused" in failed.error_message


def test_the_script_gets_exactly_the_declared_command(tmp_path: Path):
    """
    The script receives the validated values, its input file and the
    platform flags, and nothing else.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1, gfnff=True)
    client = FakeClient(job)
    run_until(make_agent(tmp_path, client), lambda: client.reports)

    session = session_folder(tmp_path / "jobs", SESSION)
    received = session / f"job_{job.job_id}" / "received.json"
    assert json.loads(received.read_text()) == {
        "input": "water.xyz",
        "jobname": "toy_opt",
        "parallel": 2,
        "charge": 1,
        "temp": 300.0,
        "gfnff": True,
        "keep": True,
        "optlevel": "normal",
        "gfn": 2,
        "solvent": None,
    }


def test_cancel_kills_the_whole_process_group(tmp_path: Path):
    """
    A cancel in the heartbeat reply stops the job (os.killpg) and is
    reported as cancelled.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    slow = assign(charge=SLOW_CHARGE)
    client = FakeClient(slow)
    client.cancel.add(slow.job_id)
    agent = make_agent(tmp_path, client)
    run_until(agent, lambda: slow.job_id in client.reports)

    assert client.reports[slow.job_id].outcome == "cancelled"
    assert not group_is_alive(agent.state.groups[0])


def test_an_abandoned_job_is_stopped_and_not_reported(tmp_path: Path):
    """
    "Abandon" (the server retried the job elsewhere) stops it quietly.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    slow = assign(charge=SLOW_CHARGE)
    client = FakeClient(slow)
    client.abandon.add(slow.job_id)
    agent = make_agent(tmp_path, client)
    run_until(
        agent,
        lambda: (
            agent.state.groups and not group_is_alive(agent.state.groups[0])
        ),
    )

    assert client.reports == {}


def test_a_job_past_its_deadline_is_stopped_and_failed(tmp_path: Path):
    """
    The agent enforces the task's time limit itself.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    slow = assign(charge=SLOW_CHARGE, deadline_seconds=0.5)
    client = FakeClient(slow)
    run_until(make_agent(tmp_path, client), lambda: client.reports)

    report = client.reports[slow.job_id]
    assert report.outcome == "failed"
    assert "limit" in report.error_message


def test_orphans_of_a_crashed_agent_are_stopped_on_restart(tmp_path: Path):
    """
    Fault test 3: processes recorded by a crashed agent are stopped when
    the next agent starts, and the state file is cleared.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    orphan = subprocess.Popen(["sleep", "60"], start_new_session=True)
    state = StateFile(tmp_path / "state.json")
    state.record("crashed-job", 1, orphan.pid)
    agent = make_agent(tmp_path, FakeClient())

    asyncio.run(agent.recover_orphans())

    assert orphan.wait(timeout=5) != 0
    assert state.load() == {}


def test_a_retry_starts_in_a_fresh_folder(tmp_path: Path):
    """
    Attempt 2 moves attempt 1's folder to ``.try1`` and starts empty
    (apart from the session's inputs).

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    artifacts = tmp_path / "jobs"
    create_session(artifacts)
    _, first = prepare_workspace(artifacts, SESSION, "42", attempt=1)
    (first / "half_written.xyz").write_text("partial")

    _, second = prepare_workspace(artifacts, SESSION, "42", attempt=2)

    assert second == first
    assert not (second / "half_written.xyz").exists()
    assert (second / "water.xyz").exists()
    retired = first.with_name("job_42.try1")
    assert (retired / "half_written.xyz").read_text() == "partial"
