"""
The agent loop: claim when a slot is free, run, heartbeat, report.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

from agent.config import AgentConfig
from agent.reports import StopReason, crash_report, exit_report, stopped_report
from agent.runner import Execution, Runner, stop_group
from agent.state import StateFile
from agent.workspace import EXECUTION_LOG, build_environment, prepare_workspace
from app.agents.schemas import (
    CompletionRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
)
from app.catalog.argv import Invocation, build_argv

logger = logging.getLogger("agent")
# Waits between attempts to deliver a result through network trouble.
REPORT_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
ERROR_BACKOFF_SECONDS = 5.0


class ApiClient(Protocol):
    """
    The calls the agent makes; ``AgentClient`` or a test double.
    """

    async def claim(self, wait_seconds: float) -> JobAssignment | None:
        """
        Ask for one job.

        :param wait_seconds: Long-poll wait.
        :type wait_seconds: float
        :return: An assignment, or None.
        :rtype: JobAssignment | None
        """

    async def heartbeat(self, held: list[JobReference]) -> HeartbeatResponse:
        """
        Report the attempts in progress.

        :param held: Attempts in progress.
        :type held: list[JobReference]
        :return: Attempts to cancel or abandon.
        :rtype: HeartbeatResponse
        """

    async def complete(self, job_id, report: CompletionRequest) -> bool:
        """
        Report how an attempt ended.

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Outcome.
        :type report: CompletionRequest
        :return: False if refused as stale.
        :rtype: bool
        """


@dataclass(slots=True)
class RunningJob:
    """
    One attempt this agent is running.

    :param assignment: What the server handed out.
    :type assignment: JobAssignment
    :param execution: Handle to the running command.
    :type execution: Execution
    :param stop_reason: Set when the agent stops the job itself.
    :type stop_reason: StopReason | None
    """

    assignment: JobAssignment
    execution: Execution
    stop_reason: StopReason | None = None

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


def invocation_for(assignment: JobAssignment) -> Invocation:
    """
    Describe one run of an assigned job for ``build_argv``.

    :param assignment: What the server handed out.
    :type assignment: JobAssignment
    :return: Values, inputs and platform-filled values.
    :rtype: Invocation
    """
    return Invocation(
        values=assignment.parameters,
        inputs=assignment.input_files,
        job_name=assignment.task.id,
        cpus=assignment.task.resources.cpus,
    )


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
        :param state: Remembers process groups across restarts.
        :type state: StateFile
        """
        self.config = config
        self.client = client
        self.runner = runner
        self.state = state
        self.slots = asyncio.Semaphore(config.max_jobs)
        self.running: dict[str, RunningJob] = {}
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
        """
        await self.recover_orphans()
        heartbeats = asyncio.create_task(self.heartbeat_loop())
        try:
            await self.claim_loop()
        finally:
            await self.stop_all()
            heartbeats.cancel()

    async def recover_orphans(self) -> None:
        """
        Stop processes a crashed predecessor left running.

        Their results cannot be trusted or collected; the server sees no
        heartbeat for them and retries each job on a new attempt.
        """
        for job_id, info in self.state.load().items():
            logger.warning("Stopping orphaned job %s from a crash", job_id)
            await stop_group(info["process_group"])
        self.state.save({})

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
            task = asyncio.create_task(self.run_job(assignment))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def claim_once(self) -> JobAssignment | None:
        """
        One claim, surviving server or network trouble.

        :return: An assignment, or None.
        :rtype: JobAssignment | None
        """
        try:
            return await self.client.claim(self.config.claim_wait_seconds)
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
        Run one attempt and report it; never let one job kill the agent.

        :param assignment: What the server handed out.
        :type assignment: JobAssignment
        """
        job_id = str(assignment.job_id)
        try:
            report = await self.execute(assignment)
        except Exception as error:  # outermost boundary for one job
            logger.exception("Job %s crashed in the agent", job_id)
            report = crash_report(assignment, error)
        finally:
            self.release(job_id)
        if report is not None:
            await self.report(assignment, report)

    def release(self, job_id: str) -> None:
        """
        Forget a finished job and free its slot.

        :param job_id: Job id.
        :type job_id: str
        """
        self.running.pop(job_id, None)
        self.state.forget(job_id)
        self.slots.release()

    async def execute(
        self, assignment: JobAssignment
    ) -> CompletionRequest | None:
        """
        Prepare the workspace, start the command, then finish it.

        :param assignment: What the server handed out.
        :type assignment: JobAssignment
        :return: The report to send, or None if the job was abandoned.
        :rtype: CompletionRequest | None
        """
        job_id = str(assignment.job_id)
        pipeline_id, workspace = prepare_workspace(
            self.config.artifacts_dir,
            assignment.parameters,
            job_id,
            assignment.attempt,
        )
        argv = build_argv(
            assignment.task, invocation_for(assignment), self.config.python_bin
        )
        environment = build_environment(self.config.pack_source_dir)
        log_path = workspace / EXECUTION_LOG
        execution = await self.runner.start(
            argv, workspace, log_path, environment
        )
        running = RunningJob(assignment, execution)
        self.running[job_id] = running
        self.state.record(job_id, assignment.attempt, execution.process_group)
        return await self.finish(running, workspace, pipeline_id)

    async def finish(
        self,
        running: RunningJob,
        workspace: Path,
        pipeline_id: str,
    ) -> CompletionRequest | None:
        """
        Wait for the command within its deadline, then build the report.

        :param running: The attempt being run.
        :type running: RunningJob
        :param workspace: Its workspace.
        :type workspace: Path
        :param pipeline_id: Its pipeline.
        :type pipeline_id: str
        :return: The report, or None if the job was abandoned.
        :rtype: CompletionRequest | None
        """
        assignment = running.assignment
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        timeout = seconds_left(assignment.deadline_at)
        try:
            return_code = await asyncio.wait_for(
                running.execution.wait(), timeout
            )
        except TimeoutError:
            running.stop_reason = running.stop_reason or StopReason.TIMEOUT
            await running.execution.terminate()
        duration = round(loop.time() - started_at, 2)
        if running.stop_reason is not None:
            return stopped_report(assignment, running.stop_reason, duration)
        return exit_report(
            assignment, return_code, workspace, pipeline_id, duration
        )

    async def report(
        self,
        assignment: JobAssignment,
        report: CompletionRequest,
    ) -> None:
        """
        Deliver a result, retrying through network trouble. A 409 means
        the server already moved on (e.g. retried the job); that is
        final, not an error.

        :param assignment: The attempt being reported.
        :type assignment: JobAssignment
        :param report: The result.
        :type report: CompletionRequest
        """
        job_id = assignment.job_id
        for delay in REPORT_RETRY_DELAYS:
            try:
                accepted = await self.client.complete(job_id, report)
            except httpx.HTTPError as error:
                logger.warning("Report failed (%s); retrying", error)
                await asyncio.sleep(delay)
                continue
            if not accepted:
                logger.info("Server refused stale report for %s", job_id)
            return
        logger.error("Gave up reporting %s; its lease will expire", job_id)

    async def heartbeat_loop(self) -> None:
        """
        Every ``heartbeat_seconds``, renew leases and obey the reply.
        """
        while not self.stopping.is_set():
            await self.pause(self.config.heartbeat_seconds)
            held = [running.reference for running in self.running.values()]
            try:
                reply = await self.client.heartbeat(held)
            except httpx.HTTPError as error:
                logger.warning("Heartbeat failed (%s)", error)
                continue
            for reference in reply.cancel:
                await self.stop(reference, StopReason.CANCELLED)
            for reference in reply.abandon:
                await self.stop(reference, StopReason.ABANDONED)

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
        for running in list(self.running.values()):
            await self.stop(running.reference, StopReason.ABANDONED)
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
