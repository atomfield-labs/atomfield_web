"""
What the agent API does: hand out jobs, keep leases alive, record
results. Routes stay thin; this module holds the rules.
"""

import asyncio
import uuid

from sqlalchemy import func, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auth import touch_target
from app.agents.schemas import (
    CompletionRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
)
from app.catalog.catalog import Catalog, UnknownTaskError
from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.models.compute_target import ComputeTarget
from app.models.job import Job
from app.queue.job_queue import RedisJobQueue
from app.runs.lifecycle import Completion, complete_attempt, start_attempt
from app.runs.states import JobStatus

# Columns an outcome may record; anything else in a report is ignored.
OUTCOME_FIELDS = {
    JobStatus.SUCCEEDED: ("output_data", "execution_time_seconds"),
    JobStatus.FAILED: ("error_message", "execution_time_seconds"),
    JobStatus.CANCELLED: ("error_message", "execution_time_seconds"),
}


async def try_start(
    db: AsyncSession,
    bus: EventBus,
    catalog: Catalog,
    target: ComputeTarget,
    job_id: uuid.UUID,
) -> JobAssignment | None:
    """
    Turn one queue message into a started attempt, if still valid.

    A message can be stale (the job was cancelled, or a duplicate was
    already claimed); then the conditional update finds nothing and the
    caller simply takes the next message.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param bus: Where the changes are announced.
    :type bus: EventBus
    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: Job id from the queue.
    :type job_id: uuid.UUID
    :return: The assignment, or None if this message was stale.
    :rtype: JobAssignment | None
    """
    job = await db.get(Job, job_id)
    if job is None or job.status != JobStatus.QUEUED:
        return None
    try:
        task = catalog.get(job.script_name)
    except UnknownTaskError:
        message = f"Task {job.script_name!r} is no longer in the catalog"
        await complete_attempt(
            db, job_id, JobStatus.FAILED, error_message=message
        )
        await commit_and_publish(db, bus)
        return None
    walltime = task.resources.walltime_minutes
    started = await start_attempt(db, job_id, walltime, agent_id=target.id)
    await commit_and_publish(db, bus)
    if started is None:
        return None
    return JobAssignment(
        job_id=started.id,
        attempt=started.attempt,
        run_id=started.run_id,
        task=task,
        parameters=started.parameters or {},
        input_files=started.input_files or {},
        deadline_at=started.deadline_at,
    )


async def claim_next(
    db: AsyncSession,
    queue: RedisJobQueue,
    bus: EventBus,
    catalog: Catalog,
    target: ComputeTarget,
    wait_seconds: float,
) -> JobAssignment | None:
    """
    Hold the request open until a job arrives or the wait runs out.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue.
    :type queue: RedisJobQueue
    :param bus: Where the changes are announced.
    :type bus: EventBus
    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param wait_seconds: Longest time to wait.
    :type wait_seconds: float
    :return: An assignment, or None if nothing arrived in time.
    :rtype: JobAssignment | None
    """
    await touch_target(db, target)
    await db.commit()
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + wait_seconds
    while (remaining := give_up_at - loop.time()) > 0:
        job_id = await queue.pop(target.id, remaining)
        if job_id is None:
            return None
        assignment = await try_start(db, bus, catalog, target, job_id)
        if assignment is not None:
            return assignment
    return None


async def record_heartbeat(
    db: AsyncSession,
    target: ComputeTarget,
    reports: list[JobReference],
) -> HeartbeatResponse:
    """
    Renew the leases an agent still holds, and tell it what to stop.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param reports: Attempts the agent says it is running.
    :type reports: list[JobReference]
    :return: Attempts to cancel, and attempts that are no longer its.
    :rtype: HeartbeatResponse
    """
    await touch_target(db, target)
    held = [(report.job_id, report.attempt) for report in reports]
    rows = []
    if held:
        statement = (
            update(Job)
            .where(
                Job.agent_id == target.id,
                Job.status == JobStatus.RUNNING,
                tuple_(Job.id, Job.attempt).in_(held),
            )
            .values(last_heartbeat_at=func.now())
            .returning(Job.id, Job.attempt, Job.cancel_requested)
        )
        rows = (await db.execute(statement)).all()
    await db.commit()
    alive = {(job_id, attempt) for job_id, attempt, _ in rows}
    return HeartbeatResponse(
        cancel=[
            JobReference(job_id=job_id, attempt=attempt)
            for job_id, attempt, cancel_requested in rows
            if cancel_requested
        ],
        abandon=[
            report
            for report in reports
            if (report.job_id, report.attempt) not in alive
        ],
    )


async def report_completion(
    db: AsyncSession,
    queue: RedisJobQueue,
    bus: EventBus,
    target: ComputeTarget,
    job_id: uuid.UUID,
    report: CompletionRequest,
) -> Completion | None:
    """
    Record how an attempt ended, then queue the children it released.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue.
    :type queue: RedisJobQueue
    :param bus: Where the changes are announced.
    :type bus: EventBus
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: Finished job.
    :type job_id: uuid.UUID
    :param report: How the attempt ended.
    :type report: CompletionRequest
    :return: The completion, or None if this agent's attempt no longer
        owns the job (stale report).
    :rtype: Completion | None
    """
    outcome = JobStatus(report.outcome)
    values = {
        field: getattr(report, field) for field in OUTCOME_FIELDS[outcome]
    }
    completion = await complete_attempt(
        db,
        job_id,
        outcome,
        expected_attempt=report.attempt,
        expected_agent=target.id,
        **values,
    )
    await commit_and_publish(db, bus)
    if completion and completion.ready:
        ready_ids = [child.id for child in completion.ready]
        await queue.add(target.id, ready_ids)
    return completion
