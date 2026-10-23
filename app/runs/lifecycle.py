"""
Create runs and move their jobs through the lifecycle.

Each event (a job starting, a job finishing) is one database
transaction: the job's own change and every consequence for its
children commit together or not at all. Callers commit, then dispatch
the jobs that became ready; a crash in between is repaired by the
sweeper, because Postgres already says those jobs are queued.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compute_target import HOUSE_TARGET_ID
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.runs.states import JobStatus
from app.runs.transitions import transition

UPSTREAM_FAILED_MESSAGE = "Upstream dependency failed"
UPSTREAM_CANCELLED_MESSAGE = "Upstream job was cancelled"
# What a job's descendants become when it ends without succeeding.
DESCENDANT_STATUS = {
    JobStatus.FAILED: (JobStatus.UPSTREAM_FAILED, UPSTREAM_FAILED_MESSAGE),
    JobStatus.CANCELLED: (JobStatus.CANCELLED, UPSTREAM_CANCELLED_MESSAGE),
}


@dataclass(frozen=True, slots=True)
class Completion:
    """
    The result of finishing one job attempt.

    :param job: The finished job.
    :type job: Job
    :param ready: Children that became queued and must be dispatched.
    :type ready: list[Job]
    """

    job: Job
    ready: list[Job]


async def create_run(
    session: AsyncSession,
    owner_id: uuid.UUID | None,
    session_id: str,
    target_id: uuid.UUID = HOUSE_TARGET_ID,
) -> Run:
    """
    Record a new submission and the machine all its jobs will run on.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param owner_id: Submitting user's API key id.
    :type owner_id: uuid.UUID | None
    :param session_id: UI session (pipeline id) the run belongs to.
    :type session_id: str
    :param target_id: Compute target; the house agent by default.
    :type target_id: uuid.UUID
    :return: The new run, flushed so its id is usable.
    :rtype: Run
    """
    run = Run(
        id=uuid.uuid4(),
        owner_id=owner_id,
        session_id=session_id,
        target_id=target_id,
    )
    session.add(run)
    await session.flush()
    return run


async def start_attempt(
    session: AsyncSession,
    job_id: uuid.UUID,
    walltime_minutes: int,
    agent_id: uuid.UUID | None = None,
) -> Job | None:
    """
    Claim a queued job: new attempt number, fresh lease, deadline.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param job_id: Job to start.
    :type job_id: uuid.UUID
    :param walltime_minutes: The task's time limit.
    :type walltime_minutes: int
    :param agent_id: Compute target that took the job.
    :type agent_id: uuid.UUID | None
    :return: The running job, or None if it was no longer queued
        (already claimed, or cancelled).
    :rtype: Job | None
    """
    return await transition(
        session,
        job_id,
        JobStatus.RUNNING,
        attempt=Job.attempt + 1,
        agent_id=agent_id,
        last_heartbeat_at=func.now(),
        deadline_at=func.now() + timedelta(minutes=walltime_minutes),
    )


async def release_children(
    session: AsyncSession,
    parent_id: uuid.UUID,
) -> list[Job]:
    """
    Count one more finished parent for each child; queue those with
    none left. One statement: every SET expression reads the old row,
    so ``pending_parents = 1`` means "this parent was the last".

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param parent_id: Job that just succeeded.
    :type parent_id: uuid.UUID
    :return: Children that became queued.
    :rtype: list[Job]
    """
    children = select(JobDependency.downstream_id).where(
        JobDependency.upstream_id == parent_id
    )
    becomes_ready = Job.pending_parents == 1
    statement = (
        update(Job)
        .where(Job.id.in_(children), Job.status == JobStatus.WAITING)
        .values(
            pending_parents=Job.pending_parents - 1,
            status=case((becomes_ready, JobStatus.QUEUED), else_=Job.status),
        )
        .returning(Job)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    result = await session.execute(statement)
    return [job for job in result.scalars() if job.status == JobStatus.QUEUED]


async def mark_descendants(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: JobStatus,
    message: str,
) -> list[uuid.UUID]:
    """
    Give every waiting descendant of a job the same final status.

    A recursive query walks the graph inside the database. Descendants
    of a job that never succeeded are always still waiting, because
    each needs that job (directly or through others) to finish first.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param job_id: Job that ended without succeeding.
    :type job_id: uuid.UUID
    :param status: UPSTREAM_FAILED or CANCELLED.
    :type status: JobStatus
    :param message: Reason shown on each descendant.
    :type message: str
    :return: Ids of the descendants that changed.
    :rtype: list[uuid.UUID]
    """
    edges = JobDependency.__table__
    descendants = (
        select(edges.c.downstream_id.label("id"))
        .where(edges.c.upstream_id == job_id)
        .cte("descendants", recursive=True)
    )
    descendants = descendants.union(
        select(edges.c.downstream_id).join(
            descendants, edges.c.upstream_id == descendants.c.id
        )
    )
    statement = (
        update(Job)
        .where(
            Job.id.in_(select(descendants.c.id)),
            Job.status == JobStatus.WAITING,
        )
        .values(status=status, error_message=message)
        .returning(Job.id)
        .execution_options(synchronize_session=False)
    )
    return list((await session.execute(statement)).scalars())


async def complete_attempt(
    session: AsyncSession,
    job_id: uuid.UUID,
    outcome: JobStatus,
    expected_attempt: int | None = None,
    expected_agent: uuid.UUID | None = None,
    extra_conditions: Sequence[ColumnElement[bool]] = (),
    **values: Any,
) -> Completion | None:
    """
    Finish a job and apply every consequence in the same transaction.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param job_id: Job that finished.
    :type job_id: uuid.UUID
    :param outcome: SUCCEEDED, FAILED or CANCELLED.
    :type outcome: JobStatus
    :param expected_attempt: Attempt the report belongs to; a report
        from an older attempt changes nothing.
    :type expected_attempt: int | None
    :param expected_agent: Agent the report comes from; only the agent
        holding the job may finish it.
    :type expected_agent: uuid.UUID | None
    :param extra_conditions: More conditions checked in the same
        statement as the status change.
    :type extra_conditions: Sequence[ColumnElement[bool]]
    :param values: Columns to record, e.g. ``output_data``,
        ``error_message``, ``execution_time_seconds``.
    :type values: Any
    :return: The finished job and newly ready children, or None if
        the job could not finish (stale attempt, already final).
    :rtype: Completion | None
    """
    job = await transition(
        session,
        job_id,
        outcome,
        expected_attempt,
        expected_agent,
        extra_conditions,
        **values,
    )
    if job is None:
        return None
    if outcome is JobStatus.SUCCEEDED:
        return Completion(job, await release_children(session, job.id))
    status, message = DESCENDANT_STATUS[outcome]
    await mark_descendants(session, job.id, status, message)
    return Completion(job, [])


async def requeue_lost(
    session: AsyncSession,
    job_id: uuid.UUID,
    attempt: int,
    lease_timeout: timedelta,
) -> Job | None:
    """
    Put a job whose agent went silent back in the queue.

    The heartbeat check is part of the same statement: if the agent
    reported in after the sweeper looked, nothing happens.

    :param session: Open database session; the caller commits and then
        dispatches the job.
    :type session: AsyncSession
    :param job_id: Job whose lease expired.
    :type job_id: uuid.UUID
    :param attempt: The attempt that was lost.
    :type attempt: int
    :param lease_timeout: Silence longer than this means "lost".
    :type lease_timeout: timedelta
    :return: The queued job, or None if it was not lost after all.
    :rtype: Job | None
    """
    return await transition(
        session,
        job_id,
        JobStatus.QUEUED,
        expected_attempt=attempt,
        extra_conditions=[lease_expired(lease_timeout)],
        agent_id=None,
        last_heartbeat_at=None,
        deadline_at=None,
    )


def lease_expired(lease_timeout: timedelta) -> ColumnElement[bool]:
    """
    Condition: the job's agent has been silent for ``lease_timeout``.

    Uses the database clock, the same clock that stamped the heartbeat,
    so a skewed server clock cannot expire leases early.

    :param lease_timeout: Allowed silence.
    :type lease_timeout: timedelta
    :return: SQL condition for use in a WHERE clause.
    :rtype: ColumnElement[bool]
    """
    return Job.last_heartbeat_at < func.now() - lease_timeout


async def request_cancel(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> JobStatus | None:
    """
    Cancel a job: at once if it has not started, else ask its agent.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param job_id: Job to cancel.
    :type job_id: uuid.UUID
    :return: CANCELLED if done now, RUNNING if the agent was asked, or
        None if the job had already finished.
    :rtype: JobStatus | None
    """
    for waiting_status in (JobStatus.WAITING, JobStatus.QUEUED):
        done = await complete_attempt(
            session,
            job_id,
            JobStatus.CANCELLED,
            extra_conditions=[Job.status == waiting_status],
            error_message="Cancelled by request",
        )
        if done is not None:
            return JobStatus.CANCELLED
    flagged = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
        .values(cancel_requested=True)
        .returning(Job.id)
    )
    return JobStatus.RUNNING if flagged.first() else None


async def dispatch(
    session: AsyncSession,
    queue: RedisJobQueue,
    jobs: Sequence[Job],
) -> None:
    """
    Send queued jobs to their runs' compute targets. Call after commit:
    a job must exist in Postgres before any agent can be told about it.

    :param session: Open database session (read only here).
    :type session: AsyncSession
    :param queue: Job queue.
    :type queue: RedisJobQueue
    :param jobs: Jobs that just became queued.
    :type jobs: Sequence[Job]
    """
    run_ids = {job.run_id for job in jobs}
    if not run_ids:
        return
    query = select(Run.id, Run.target_id).where(Run.id.in_(run_ids))
    target_of = dict((await session.execute(query)).all())
    by_target: dict[uuid.UUID, list[uuid.UUID]] = {}
    for job in jobs:
        by_target.setdefault(target_of[job.run_id], []).append(job.id)
    for target_id, job_ids in by_target.items():
        await queue.add(target_id, job_ids)
