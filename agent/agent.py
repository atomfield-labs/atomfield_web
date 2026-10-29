"""
The agent loop: claim a job whenever a slot is free, run it, keep its
lease alive with heartbeats, report it. This class only coordinates;
the work is done by its parts:

- ``Preparer``: scripts, data packs, the job's folder, its inputs and
  command (``agent.preparer``);
- ``Runner``: starts, watches and stops commands (``agent.runner``,
  ``agent.slurm``);
- ``Reporter``: the job's files and the delivery of its report
  (``agent.reporter``);
- ``Bundler``: zips runs when the server asks (``agent.bundler``).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

from agent.bundler import BundleApi, Bundler
from agent.config import AgentConfig
from agent.preparer import Preparer
from agent.reporter import Reporter, ResultsApi
from agent.reports import StopReason, crash_report, exit_report, stopped_report
from agent.runner import Execution, Runner
from agent.state import StateFile
from agent.workspace import job_folder
from app.agents.schemas import (
    CompletionRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
)

logger = logging.getLogger("agent")
ERROR_BACKOFF_SECONDS = 5.0
# How often, between heartbeats, the agent looks for a job that has
# just started: the server hears of it at once, not at the next beat.
START_CHECK_SECONDS = 1.0


class ApiClient(ResultsApi, BundleApi, Protocol):
    """
    Every call the agent and its parts make; ``AgentClient`` or a test
    double. Each part depends only on the calls it uses.
    """

    async def claim(
        self, wait_seconds: float, scheduled: bool
    ) -> JobAssignment | None:
        """
        Ask for one job.

        :param wait_seconds: Long-poll wait.
        :type wait_seconds: float
        :param scheduled: Jobs go to a scheduler and may queue there.
        :type scheduled: bool
        :return: An assignment, or None.
        :rtype: JobAssignment | None
        """

    async def heartbeat(
        self,
        held: list[JobReference],
        started: list[JobReference],
    ) -> HeartbeatResponse:
        """
        Report the attempts in progress, and which have begun running.

        :param held: Attempts in progress.
        :type held: list[JobReference]
        :param started: Those that have begun running.
        :type started: list[JobReference]
        :return: Attempts to cancel or abandon.
        :rtype: HeartbeatResponse
        """

    async def download(self, url: str, destination: Path) -> None:
        """
        Save what a signed link serves.

        :param url: Signed download link.
        :type url: str
        :param destination: File to create.
        :type destination: Path
        """


@dataclass(slots=True)
class RunningJob:
    """
    One attempt this agent is running.

    :param assignment: What the server handed out.
    :type assignment: JobAssignment
    :param execution: Handle to the running command.
    :type execution: Execution
    :param workspace: The job's folder.
    :type workspace: Path
    :param stop_reason: Set when the agent stops the job itself.
    :type stop_reason: StopReason | None
    :param holds_slot: Whether it took one of the agent's job slots
        (a job taken over from a previous agent may run without one).
    :type holds_slot: bool
    """

    assignment: JobAssignment
    execution: Execution
    workspace: Path
    stop_reason: StopReason | None = None
    holds_slot: bool = True

    @property
    def reference(self) -> JobReference:
        """
        This attempt, as the API refers to it.

        :return: Job id and attempt number.
        :rtype: JobReference
        """
        return JobReference(
            job_id=self.assignment.job_id, attempt=self.assignment.attempt
        )


def seconds_left(deadline: datetime) -> float:
    """
    Time until a deadline, never negative.

    :param deadline: Aware deadline from the server.
    :type deadline: datetime
    :return: Seconds remaining.
    :rtype: float
    """
    return max(0.0, (deadline - datetime.now(UTC)).total_seconds())


class Agent:
    """
    Runs jobs for one compute target until asked to stop.
    """

    def __init__(
        self,
        config: AgentConfig,
        client: ApiClient,
        runner: Runner,
        state: StateFile,
    ) -> None:
        """
        Assemble an agent from its parts.

        :param config: Agent settings.
        :type config: AgentConfig
        :param client: Agent API client.
        :type client: ApiClient
        :param runner: Starts commands.
        :type runner: Runner
        :param state: Remembers jobs across restarts.
        :type state: StateFile
        """
        self.config = config
        self.client = client
        self.runner = runner
        self.state = state
        self.preparer = Preparer(config, client.download)
        self.reporter = Reporter(config, client)
        self.bundler = Bundler(config, client)
        self.slots = asyncio.Semaphore(config.max_jobs)
        self.running: dict[str, RunningJob] = {}
        # Jobs whose start the server has been told about.
        self.reported_starts: set[str] = set()
        self.tasks: set[asyncio.Task] = set()
        self.stopping = asyncio.Event()

    def request_stop(self) -> None:
        """
        Ask the agent to stop (safe to call from a signal handler).
        """
        self.stopping.set()

    async def run(self) -> None:
        """
        Recover from a previous crash, then work until asked to stop.
        Heartbeats and claims run side by side, and either one ending
        (a stop request, or an error such as a refused token) ends
        both: a stop never waits for a job slot to free up.

        :raises TokenRefusedError: If the API refused this agent's
            token.
        """
        await self.recover_jobs()
        loops = {
            asyncio.create_task(self.heartbeat_loop()),
            asyncio.create_task(self.claim_loop()),
        }
        try:
            done, _ = await asyncio.wait(
                loops, return_when=asyncio.FIRST_COMPLETED
            )
            for loop in done:
                loop.result()
        finally:
            await self.shut_down(loops)

    async def shut_down(self, loops: set[asyncio.Task]) -> None:
        """
        End both loops and leave the jobs as ``stop_all`` says.

        :param loops: The heartbeat and claim loops.
        :type loops: set[asyncio.Task]
        """
        self.request_stop()
        for loop in loops:
            loop.cancel()
        await self.stop_all()
        await self.runner.close()

    async def recover_jobs(self) -> None:
        """
        Deal with the jobs a previous agent left: the runner stops a
        local orphan (its results cannot be trusted; the server retries
        it) or takes over a Slurm job, which is then watched and
        reported like any other.
        """
        for job_id, entry in self.state.load().items():
            handle, assignment, workspace = self.left_behind(entry)
            execution = await self.runner.adopt(handle, workspace)
            if execution is None or assignment is None:
                logger.warning("Stopped job %s left by a crash", job_id)
                self.state.forget(job_id)
                continue
            logger.info("Took over job %s (%s)", job_id, handle)
            await self.take_over(
                job_id, RunningJob(assignment, execution, workspace)
            )

    def left_behind(
        self, entry: dict
    ) -> tuple[str, JobAssignment | None, Path]:
        """
        What the state file says about a job a previous agent left.

        :param entry: The job's entry in the state file.
        :type entry: dict
        :return: Its runner handle, its assignment (if saved) and its
            folder.
        :rtype: tuple[str, JobAssignment | None, Path]
        """
        handle = str(entry.get("handle", entry.get("process_group")))
        saved = entry.get("assignment")
        assignment = JobAssignment.model_validate(saved) if saved else None
        workspace = (
            job_folder(self.config.artifacts_dir, assignment)
            if assignment
            else self.config.artifacts_dir
        )
        return handle, assignment, workspace

    async def take_over(self, job_id: str, running: RunningJob) -> None:
        """
        Watch and report a job a previous agent left running. It is
        already running, so it takes a free slot but never waits for
        one (there may be fewer slots now than jobs left running).

        :param job_id: The job.
        :type job_id: str
        :param running: The job and its execution.
        :type running: RunningJob
        """
        running.holds_slot = not self.slots.locked()
        if running.holds_slot:
            await self.slots.acquire()
        self.running[job_id] = running
        self.spawn(self.see_through(running.assignment, self.conclude(running)))

    async def claim_loop(self) -> None:
        """
        Claim a job whenever a slot is free, until asked to stop.
        """
        while not self.stopping.is_set():
            await self.slots.acquire()
            assignment = await self.claim_once()
            if assignment is None:
                self.slots.release()
                continue
            self.spawn(self.run_job(assignment))

    def spawn(self, job_work) -> None:
        """
        Run one job's work in the background, kept until it is done.

        :param job_work: Coroutine that runs and reports one job.
        :type job_work: Coroutine
        """
        task = asyncio.create_task(job_work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def claim_once(self) -> JobAssignment | None:
        """
        One claim, surviving server or network trouble.

        :return: An assignment, or None.
        :rtype: JobAssignment | None
        """
        try:
            return await self.client.claim(
                self.config.claim_wait_seconds, self.runner.scheduled
            )
        except httpx.HTTPError as error:
            logger.warning("Claim failed (%s); retrying shortly", error)
            await self.pause(ERROR_BACKOFF_SECONDS)
            return None

    async def pause(self, seconds: float) -> None:
        """
        Sleep, but wake at once if asked to stop.

        :param seconds: How long to sleep.
        :type seconds: float
        """
        try:
            await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def run_job(self, assignment: JobAssignment) -> None:
        """
        Run one attempt and report it.

        :param assignment: What the server handed out.
        :type assignment: JobAssignment
        """
        await self.see_through(assignment, self.execute(assignment))

    async def see_through(self, assignment: JobAssignment, job_work) -> None:
        """
        Await one job's work and report it; never let one job kill the
        agent. If the agent is stopping (the work is cancelled), the
        job stays in the state file for the next agent.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :param job_work: Coroutine returning the report (or None).
        :type job_work: Coroutine
        """
        job_id = str(assignment.job_id)
        try:
            report = await job_work
        except Exception as error:  # outermost boundary for one job
            logger.exception("Job %s crashed in the agent", job_id)
            report = crash_report(assignment, error)
        self.release(job_id)
        if report is not None:
            recorded = await self.reporter.deliver(assignment, report)
            if recorded is not None:
                self.bundler.start(recorded.pack)

    def release(self, job_id: str) -> None:
        """
        Forget a finished job and free its slot.

        :param job_id: Job id.
        :type job_id: str
        """
        running = self.running.pop(job_id, None)
        self.reported_starts.discard(job_id)
        self.state.forget(job_id)
        if running is None or running.holds_slot:
            self.slots.release()

    async def execute(
        self, assignment: JobAssignment
    ) -> CompletionRequest | None:
        """
        Prepare the job, start its command, then finish it.

        :param assignment: What the server handed out.
        :type assignment: JobAssignment
        :return: The report to send, or None if the job was abandoned.
        :rtype: CompletionRequest | None
        """
        job_id = str(assignment.job_id)
        prepared = await self.preparer.prepare(assignment)
        execution = await self.runner.start(prepared.command)
        running = RunningJob(assignment, execution, prepared.workspace)
        self.running[job_id] = running
        self.state.record(
            job_id,
            assignment.attempt,
            execution.handle,
            assignment.model_dump(mode="json"),
        )
        return await self.conclude(running)

    async def conclude(self, running: RunningJob) -> CompletionRequest | None:
        """
        Wait for a started (or taken over) job, then build its report
        with its files.

        :param running: The job.
        :type running: RunningJob
        :return: The report, or None if the job was abandoned.
        :rtype: CompletionRequest | None
        """
        report = await self.finish(running)
        if report is None:
            return None
        return await self.reporter.attach_results(
            running.assignment, running.workspace, report
        )

    async def finish(self, running: RunningJob) -> CompletionRequest | None:
        """
        Wait for the command within its deadline, then build the report.

        :param running: The attempt being run.
        :type running: RunningJob
        :return: The report, or None if the job was abandoned.
        :rtype: CompletionRequest | None
        """
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        return_code = await self.wait_for_exit(running)
        duration = round(loop.time() - started_at, 2)
        assignment = running.assignment
        if running.stop_reason is not None:
            return stopped_report(assignment, running.stop_reason, duration)
        return exit_report(assignment, return_code, running.workspace, duration)

    def time_limit(self, assignment: JobAssignment) -> float | None:
        """
        Seconds a job may still run here. None under a scheduler
        (Slurm): it times its jobs from when they really start; the
        agent times only its own children.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :return: Seconds left, or None for no limit here.
        :rtype: float | None
        """
        if self.runner.scheduled:
            return None
        return seconds_left(assignment.deadline_at)

    async def wait_for_exit(self, running: RunningJob) -> int | None:
        """
        Wait for the command, stopping it at its time limit; a stop
        for time is noted on the job.

        :param running: The attempt being run.
        :type running: RunningJob
        :return: Its exit code, or None if it was stopped for time.
        :rtype: int | None
        """
        timeout = self.time_limit(running.assignment)
        try:
            return_code = await asyncio.wait_for(
                running.execution.wait(), timeout
            )
        except TimeoutError:
            running.stop_reason = running.stop_reason or StopReason.TIMEOUT
            await running.execution.terminate()
            return None
        if running.execution.timed_out:
            running.stop_reason = running.stop_reason or StopReason.TIMEOUT
        return return_code

    async def heartbeat_loop(self) -> None:
        """
        Renew leases and obey the reply: every ``heartbeat_seconds``,
        and as soon as a job starts, so the web app shows it running
        without waiting for the next beat.
        """
        while not self.stopping.is_set():
            await self.wait_for_beat()
            await self.beat()

    async def wait_for_beat(self) -> None:
        """
        Sleep until the next heartbeat is due, or until a job has
        started that the server has not heard about yet.
        """
        loop = asyncio.get_running_loop()
        due = loop.time() + self.config.heartbeat_seconds
        while not self.stopping.is_set() and loop.time() < due:
            if self.unreported_starts():
                return
            await self.pause(min(START_CHECK_SECONDS, due - loop.time()))

    def unreported_starts(self) -> list[str]:
        """
        Jobs that have started but whose start was not reported yet.

        :return: Their job ids.
        :rtype: list[str]
        """
        return [
            job_id
            for job_id, running in self.running.items()
            if running.execution.started and job_id not in self.reported_starts
        ]

    async def beat(self) -> None:
        """
        One heartbeat: renew leases, report started jobs, obey the
        reply (cancel, abandon, zip). After a failure, wait a little,
        so a server outage is not hammered.
        """
        held = [running.reference for running in self.running.values()]
        started = [
            running.reference
            for running in self.running.values()
            if running.execution.started
        ]
        try:
            reply = await self.client.heartbeat(held, started)
        except httpx.HTTPError as error:
            logger.warning("Heartbeat failed (%s)", error)
            await self.pause(ERROR_BACKOFF_SECONDS)
            return
        self.reported_starts.update(str(ref.job_id) for ref in started)
        for reference in reply.cancel:
            await self.stop(reference, StopReason.CANCELLED)
        for reference in reply.abandon:
            await self.stop(reference, StopReason.ABANDONED)
        self.bundler.start(reply.pack)

    async def stop(self, reference: JobReference, reason: StopReason) -> None:
        """
        Stop one attempt, if this agent is still running it.

        :param reference: Attempt to stop.
        :type reference: JobReference
        :param reason: Why; decides what gets reported.
        :type reason: StopReason
        """
        running = self.running.get(str(reference.job_id))
        if running is None or running.assignment.attempt != reference.attempt:
            return
        if running.stop_reason is None:
            running.stop_reason = reason
            await running.execution.terminate()

    async def stop_all(self) -> None:
        """
        On shutdown, stop every job without reporting; the server will
        retry them when their leases expire.
        """
        if self.runner.scheduled:
            # Slurm keeps the jobs running; they stay in the state file
            # and the next agent takes them over.
            for task in self.tasks:
                task.cancel()
        else:
            for running in list(self.running.values()):
                await self.stop(running.reference, StopReason.ABANDONED)
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.bundler.close()
