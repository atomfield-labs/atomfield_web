"""
The agent program, against a fake API client and real subprocesses:
reports, cancel, abandon, deadlines, crash recovery and fresh folders.
"""

import asyncio
import dataclasses
import hashlib
import io
import json
import subprocess
import sys
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from agent.agent import Agent
from agent.config import AgentConfig
from agent.runner import ProcessRunner, Runner, group_is_alive
from agent.slurm import SlurmRunner, SlurmSettings
from agent.state import StateFile
from agent.workspace import prepare_workspace, run_folder
from app.agents.schemas import (
    UI_FILE_MAX_BYTES,
    BundleReport,
    CompletionRequest,
    CompletionResponse,
    HeartbeatResponse,
    InputFile,
    JobAssignment,
    JobReference,
    PackRequest,
    UploadLinksResponse,
)
from app.catalog.catalog import Catalog
from tests.fake_pack import SLOW_CHARGE, WATER_XYZ, install_fake_pack
from tests.fake_slurm import install_fake_slurm

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
CATALOG = Catalog.from_path(FIXTURE)
SESSION = {"pipeline_id": "session_1", "user_id": "user_1"}
WATER = InputFile(name="water.xyz", url="/fake-store/water.xyz")
MISSING_URL = "/fake-store/missing.xyz"


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
        node_key="opt",
        task=CATALOG.get("toy_opt"),
        parameters={**values, **SESSION},
        input_files={"structure": ["water.xyz"]},
        inputs=[WATER],
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
        self.started: set[uuid.UUID] = set()
        self.scheduled: bool | None = None
        self.uploads: dict[str, bytes] = {}
        self.stale_uploads = False
        self.packs: list[PackRequest] = []
        self.files: dict[str, bytes] = {}
        self.bundles: dict[uuid.UUID, BundleReport] = {}
        # What links serve besides water.xyz, and every link fetched.
        self.served: dict[str, bytes] = {}
        self.downloads: list[str] = []

    async def claim(
        self, wait_seconds: float, scheduled: bool = False
    ) -> JobAssignment | None:
        """
        Hand out the next assignment, or wait briefly and return None.

        :param wait_seconds: Ignored long-poll wait.
        :type wait_seconds: float
        :param scheduled: Recorded: whether the agent's jobs queue.
        :type scheduled: bool
        :return: The next assignment, if any.
        :rtype: JobAssignment | None
        """
        self.scheduled = scheduled
        if self.pending:
            return self.pending.pop(0)
        await asyncio.sleep(0.02)
        return None

    async def heartbeat(
        self,
        held: list[JobReference],
        started: list[JobReference] | None = None,
    ) -> HeartbeatResponse:
        """
        Echo back which held attempts to cancel or abandon; remember
        which were reported running.

        :param held: Attempts the agent is running.
        :type held: list[JobReference]
        :param started: Those that have begun running.
        :type started: list[JobReference] | None
        :return: Instructions.
        :rtype: HeartbeatResponse
        """
        self.started.update(ref.job_id for ref in started or [])
        return HeartbeatResponse(
            cancel=[ref for ref in held if ref.job_id in self.cancel],
            abandon=[ref for ref in held if ref.job_id in self.abandon],
        )

    async def download(self, url: str, destination: Path) -> None:
        """
        Serve what ``served`` holds for a link, else water.xyz; a 404
        for ``MISSING_URL``.

        :param url: Signed link.
        :type url: str
        :param destination: File to create.
        :type destination: Path
        :raises httpx.HTTPStatusError: For the missing file.
        """
        self.downloads.append(url)
        if url in self.served:
            destination.write_bytes(self.served[url])
            return
        if url == MISSING_URL:
            request = httpx.Request("GET", url)
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError(
                "404", request=request, response=response
            )
        destination.write_text(WATER_XYZ)

    async def upload_links(
        self,
        job_id,
        attempt: int,
        names: list[str],
    ) -> UploadLinksResponse | None:
        """
        Grant a fake link per name, or nothing when set to be stale.

        :param job_id: The job.
        :type job_id: uuid.UUID
        :param attempt: Its attempt.
        :type attempt: int
        :param names: File names.
        :type names: list[str]
        :return: Links, or None (stale).
        :rtype: UploadLinksResponse | None
        """
        if self.stale_uploads:
            return None
        links = {name: f"/fake-upload/{name}" for name in names}
        return UploadLinksResponse(links=links, max_bytes=UI_FILE_MAX_BYTES)

    async def upload(self, url: str, content: bytes) -> None:
        """
        Keep what was uploaded, by file name.

        :param url: Fake link.
        :type url: str
        :param content: Uploaded bytes.
        :type content: bytes
        """
        self.uploads[url.removeprefix("/fake-upload/")] = content

    async def complete(
        self, job_id, report: CompletionRequest
    ) -> CompletionResponse:
        """
        Record a report; the reply carries the configured pack requests
        (as when a report finishes a run).

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Outcome.
        :type report: CompletionRequest
        :return: Accepted, with any runs to zip.
        :rtype: CompletionResponse
        """
        self.reports[job_id] = report
        packs, self.packs = self.packs, []
        return CompletionResponse(
            job_id=job_id, status=report.outcome, children_queued=0, pack=packs
        )

    async def upload_file(self, url: str, source: Path) -> None:
        """
        Keep an uploaded zip's bytes by link.

        :param url: Fake link.
        :type url: str
        :param source: The zip.
        :type source: Path
        """
        self.files[url] = source.read_bytes()

    async def report_bundle(self, run_id, report: BundleReport) -> bool:
        """
        Record how packing ended.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param report: Outcome.
        :type report: BundleReport
        :return: Always accepted.
        :rtype: bool
        """
        self.bundles[run_id] = report
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

    def record(
        self,
        job_id: str,
        attempt: int,
        handle: str,
        assignment: dict | None = None,
    ) -> None:
        """
        Remember the job, noting its process group.

        :param job_id: Job id.
        :type job_id: str
        :param attempt: Attempt number.
        :type attempt: int
        :param handle: Its process group.
        :type handle: str
        :param assignment: The assignment as JSON.
        :type assignment: dict | None
        """
        self.groups.append(int(handle))
        super().record(job_id, attempt, handle, assignment)


def make_agent(
    tmp_path: Path,
    client: FakeClient,
    runner: Runner | None = None,
    own_copy: bool = True,
    **changes,
) -> Agent:
    """
    An agent with fast timers, running the fake pack in tmp_path.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    :param client: Fake API client.
    :type client: FakeClient
    :param runner: How jobs run; local processes by default.
    :type runner: Runner | None
    :param own_copy: Run the fake pack as the owner's own copy; else
        jobs run the release they name.
    :type own_copy: bool
    :param changes: Other settings, e.g. ``delete_after_upload=True``.
    :type changes: Any
    :return: Ready agent.
    :rtype: Agent
    """
    config = AgentConfig(
        api_url="http://unused",
        token="unused",
        python_bin=sys.executable,
        pack_source_dir=install_fake_pack(tmp_path) if own_copy else None,
        artifacts_dir=tmp_path / "jobs",
        state_file=tmp_path / "state.json",
        heartbeat_seconds=0.05,
        claim_wait_seconds=0.05,
    )
    config = dataclasses.replace(config, **changes)
    state = RecordingState(config.state_file)
    return Agent(config, client, runner or ProcessRunner(), state)


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

    folder = run_folder(tmp_path / "jobs", job.run_id) / job.node_key
    received = folder / "received.json"
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
    state.record("crashed-job", 1, str(orphan.pid))
    agent = make_agent(tmp_path, FakeClient())

    asyncio.run(agent.recover_jobs())

    assert orphan.wait(timeout=5) != 0
    assert state.load() == {}


def test_a_retry_starts_in_a_fresh_folder(tmp_path: Path):
    """
    Attempt 2 moves attempt 1's folder to ``<node>.try1`` and starts
    empty.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    first_try = assign()
    first = prepare_workspace(tmp_path, first_try)
    (first / "half_written.xyz").write_text("partial")

    second = prepare_workspace(
        tmp_path, first_try.model_copy(update={"attempt": 2})
    )

    assert second == first
    assert list(second.iterdir()) == []
    retired = first.with_name("opt.try1")
    assert (retired / "half_written.xyz").read_text() == "partial"


def test_a_missing_input_fails_the_job_with_its_name(tmp_path: Path):
    """
    An input whose link no longer works fails the job with a message
    naming the file, instead of running the script without it.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign()
    gone = InputFile(name="water.xyz", url=MISSING_URL)
    job = job.model_copy(update={"inputs": [gone]})
    client = FakeClient(job)
    run_until(make_agent(tmp_path, client), lambda: client.reports)

    report = client.reports[job.job_id]
    assert report.outcome == "failed"
    assert "Could not download input 'water.xyz'" in report.error_message


def test_a_report_carries_file_cards_location_and_ui_files(tmp_path: Path):
    """
    The report lists every file with its fingerprint and says where the
    run's folder is; small text files are uploaded, the log first.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    agent = make_agent(tmp_path, client)
    run_until(agent, lambda: client.reports)

    report = client.reports[job.job_id]
    folder = run_folder(tmp_path / "jobs", job.run_id)
    assert report.folder.path == str(folder)
    cards = {card.path: card for card in report.files}
    output = folder / "opt" / "toy_opt_optimized.xyz"
    assert cards["toy_opt_optimized.xyz"].size_bytes == output.stat().st_size
    expected = hashlib.sha256(output.read_bytes()).hexdigest()
    assert cards["toy_opt_optimized.xyz"].sha256 == expected
    assert cards["execution.log"].uploaded
    assert client.uploads["toy_opt_optimized.xyz"] == output.read_bytes()


def test_a_stale_attempt_uploads_nothing_but_still_reports(tmp_path: Path):
    """
    If the server refuses upload links (the attempt went stale), the
    report is still sent, with every card marked not uploaded.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    client.stale_uploads = True
    run_until(make_agent(tmp_path, client), lambda: client.reports)

    report = client.reports[job.job_id]
    assert report.outcome == "succeeded"
    assert report.files
    assert not any(card.uploaded for card in report.files)
    assert client.uploads == {}


def pack_request(job: JobAssignment) -> PackRequest:
    """
    A request to zip the run of ``job``, as a reply would carry it.

    :param job: Any job of the run.
    :type job: JobAssignment
    :return: Pack request with a fake upload link.
    :rtype: PackRequest
    """
    return PackRequest(
        run_id=job.run_id,
        bundle_name="water_run",
        upload_url="/fake-store/bundle.zip",
        max_bytes=10_000_000,
        manifest={"run_id": str(job.run_id), "jobs": [{"node": "opt"}]},
    )


def test_a_run_finished_by_a_report_is_zipped_and_uploaded(tmp_path: Path):
    """
    The reply to the report that finished the run asks for its zip:
    the agent zips the run folder with run.json, uploads it, reports
    it ready, and removes its local copy of the zip.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    client.packs = [pack_request(job)]
    run_until(make_agent(tmp_path, client), lambda: client.bundles)

    report = client.bundles[job.run_id]
    archive = zipfile.ZipFile(
        io.BytesIO(client.files["/fake-store/bundle.zip"])
    )
    names = archive.namelist()
    assert report.status == "ready"
    assert report.size_bytes == len(client.files["/fake-store/bundle.zip"])
    assert "water_run/run.json" in names
    assert "water_run/opt/toy_opt_optimized.xyz" in names
    assert not any(name.endswith(".part") for name in names)
    leftovers = list((tmp_path / "jobs" / "runs").glob(".*"))
    assert leftovers == []


def test_the_house_agent_removes_a_run_folder_once_uploaded(tmp_path: Path):
    """
    With ``delete_after_upload`` (the house agent: our disk), the run's
    folder goes once its zip is safely uploaded.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    client.packs = [pack_request(job)]
    agent = make_agent(tmp_path, client, delete_after_upload=True)
    run_until(agent, lambda: client.bundles)

    assert client.bundles[job.run_id].status == "ready"
    assert not run_folder(tmp_path / "jobs", job.run_id).exists()


def test_a_zip_over_the_limit_is_reported_too_big(tmp_path: Path):
    """
    Writing stops past the limit; nothing is uploaded and the server
    is told the zip is too big.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    tiny = pack_request(job).model_copy(update={"max_bytes": 10})
    client.packs = [tiny]
    run_until(make_agent(tmp_path, client), lambda: client.bundles)

    assert client.bundles[job.run_id].status == "too_big"
    assert client.files == {}


def slurm(tmp_path: Path, **switches: str) -> SlurmRunner:
    """
    A Slurm runner on fake Slurm commands, polling fast.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    :param switches: ``FAKE_SLURM_*`` settings.
    :type switches: str
    :return: Runner.
    :rtype: SlurmRunner
    """
    environment = {**install_fake_slurm(tmp_path / "slurm"), **switches}
    return SlurmRunner(
        SlurmSettings(poll_seconds=0.05, environment=environment)
    )


def test_a_job_runs_through_slurm_to_success(tmp_path: Path):
    """
    The claim says this agent's jobs queue; the job goes through
    Slurm (its batch script in the job's folder) and the report carries
    its files.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    run_until(
        make_agent(tmp_path, client, slurm(tmp_path)), lambda: client.reports
    )

    report = client.reports[job.job_id]
    assert client.scheduled is True
    assert report.outcome == "succeeded"
    assert any(card.path == "toy_opt_optimized.xyz" for card in report.files)
    folder = run_folder(tmp_path / "jobs", job.run_id) / "opt"
    assert (folder / "job.sbatch").exists()


def test_a_running_slurm_job_is_reported_started_and_can_be_cancelled(
    tmp_path: Path,
):
    """
    Once Slurm runs the job, heartbeats say so (the server then starts
    its clock); a cancel goes through ``scancel``.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=SLOW_CHARGE)
    client = FakeClient(job)

    def started_then_cancelled() -> bool:
        if job.job_id in client.started:
            client.cancel.add(job.job_id)
        return job.job_id in client.reports

    run_until(
        make_agent(tmp_path, client, slurm(tmp_path)), started_then_cancelled
    )

    assert job.job_id in client.started
    assert client.reports[job.job_id].outcome == "cancelled"


def test_a_slurm_job_outlives_its_agent_and_is_adopted(tmp_path: Path):
    """
    The agent stops while its job waits in Slurm's queue: the job is
    left running and remembered. A new agent takes it over and reports
    it, though it never claimed it.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    first_client = FakeClient(job)
    runner = slurm(tmp_path, FAKE_SLURM_PENDING_SECONDS="1")
    first = make_agent(tmp_path, first_client, runner)
    run_until(first, lambda: first.state.load())

    assert first_client.reports == {}
    assert str(job.job_id) in first.state.load()

    second_client = FakeClient()
    second = make_agent(tmp_path, second_client, SlurmRunner(runner.settings))
    run_until(second, lambda: second_client.reports)

    assert second_client.reports[job.job_id].outcome == "succeeded"
    assert second.state.load() == {}


def test_slurm_stopping_a_job_at_its_limit_fails_it_as_timed_out(
    tmp_path: Path,
):
    """
    When Slurm ends a job at ``--time`` (state TIMEOUT), the report is
    the usual time-limit failure.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1)
    client = FakeClient(job)
    runner = slurm(tmp_path, FAKE_SLURM_FINAL_STATE="TIMEOUT")
    run_until(make_agent(tmp_path, client, runner), lambda: client.reports)

    report = client.reports[job.job_id]
    assert report.outcome == "failed"
    assert "limit" in report.error_message
