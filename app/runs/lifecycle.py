"""
Create runs and move their jobs through the lifecycle.

Each event (a job starting, a job finishing) is one database
transaction: the job's own change and every consequence for its
children commit together or not at all. Every status change is noted
(``record_changes``); callers commit with ``commit_and_publish``, which
numbers and announces the changes, then dispatch the jobs that became
ready. A crash in between is repaired by the sweeper, because Postgres
already says those jobs are queued.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    Update,
    case,
    func,
    literal,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.changes import record_changes
from app.models.compute_target import HOUSE_TARGET_ID
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.runs.states import NOT_STARTED_STATUSES, JobStatus
from app.runs.transitions import (
    fresh_rows,
    held_by,
    transition,
    update_job,
    update_jobs,
)

UPSTREAM_FAILED_MESSAGE = "Upstream dependency failed"
UPSTREAM_CANCELLED_MESSAGE = "Upstream job was cancelled"
CANCELLED_MESSAGE = "Cancelled by request"
# What a job's descendants become when it ends without succeeding.
DESCENDANT_STATUS = {
    JobStatus.FAILED: (JobStatus.UPSTREAM_FAILED, UPSTREAM_FAILED_MESSAGE),
    JobStatus.CANCELLED: (JobStatus.CANCELLED, UPSTREAM_CANCELLED_MESSAGE),
}
# What a job holds only during an attempt; a job back in the queue has
# none of it (no agent, lease, start or deadline).
BETWEEN_ATTEMPTS = MappingProxyType(
    {
        "agent_id": None,
        "last_heartbeat_at": None,
        "started_at": None,
        "deadline_at": None,
    }
)


@dataclass(frozen=True, slots=True)
class SilenceLimits:
    """
    How long an agent may stay silent before its jobs count as lost.

    :param local: For jobs that die with their agent (its own child
        processes): retry quickly.
    :type local: timedelta
    :param scheduled: For jobs a scheduler (Slurm) keeps running
        without the agent: wait, so a crashed agent can come back and
        take them over instead of losing hours of work.
    :type scheduled: timedelta
    """

    local: timedelta
    scheduled: timedelta


@dataclass(frozen=True, slots=True)
class RunCancel:
    """
    What cancelling a run did.

    :param cancelled: Jobs cancelled at once (not started yet).
    :type cancelled: int
    :param cancelling: Running jobs whose agents were asked to stop.
    :type cancelling: int
    """

    cancelled: int
    cancelling: int


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
    release_id: uuid.UUID | None = None,
) -> Run:
    """
    Record a new submission, the machine all its jobs will run on, and
    the scripts release they all use.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param owner_id: Submitting user's API key id.
    :type owner_id: uuid.UUID | None
    :param session_id: UI session (pipeline id) the run belongs to.
    :type session_id: str
    :param target_id: Compute target; the house agent by default.
    :type target_id: uuid.UUID
    :param release_id: Scripts release; None before the first release.
    :type release_id: uuid.UUID | None
    :return: The new run, flushed so its id is usable.
    :rtype: Run
    """
    run = Run(
        id=uuid.uuid4(),
        owner_id=owner_id,
        session_id=session_id,
        target_id=target_id,
        release_id=release_id,
    )
    session.add(run)
    await session.flush()
    return run


def deadline_from_now(walltime_minutes: int) -> ColumnElement[Any]:
    """
    A deadline one task time limit from now, on the database clock.

    :param walltime_minutes: The task's time limit.
    :type walltime_minutes: int
    :return: SQL expression for the deadline.
    :rtype: ColumnElement[Any]
    """
    return func.now() + timedelta(minutes=walltime_minutes)


async def start_attempt(
    session: AsyncSession,
    job_id: uuid.UUID,
    walltime_minutes: int,
    agent_id: uuid.UUID | None = None,
    scheduled: bool = False,
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
    :param scheduled: The agent hands jobs to a scheduler: the job may
        queue there, so its start time and deadline are set when the
        agent reports it running (``mark_started``).
    :type scheduled: bool
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
        scheduled=scheduled,
        started_at=None if scheduled else func.now(),
        deadline_at=None if scheduled else deadline_from_now(walltime_minutes),
    )


async def mark_started(
    session: AsyncSession,
    job_id: uuid.UUID,
    attempt: int,
    agent_id: uuid.UUID,
    walltime_minutes: int,
) -> Job | None:
    """
    Record that a scheduler began running a job the agent submitted:
    its start time, and its deadline from now. Only the first report
    counts, and only from the attempt and agent that hold the job.

    :param session: Open database session; the caller commits with
        ``commit_and_publish``, which announces the change.
    :type session: AsyncSession
    :param job_id: The job.
    :type job_id: uuid.UUID
    :param attempt: The attempt that started.
    :type attempt: int
    :param agent_id: The reporting agent's target.
    :type agent_id: uuid.UUID
    :param walltime_minutes: The task's time limit.
    :type walltime_minutes: int
    :return: The job, or None if nothing changed.
    :rtype: Job | None
    """
    statement = (
        update(Job)
        .where(*held_by(job_id, attempt, agent_id), Job.started_at.is_(None))
        .values(
            started_at=func.now(),
            deadline_at=deadline_from_now(walltime_minutes),
        )
    )
    return await update_job(session, statement)


async def release_children(
    session: AsyncSession,
    parent_id: uuid.UUID,
) -> list[Job]:
    """
    Count one more finished parent for each child; queue those with
    none left.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param parent_id: Job that just succeeded.
    :type parent_id: uuid.UUID
    :return: Children that became queued.
    :rtype: list[Job]
    """
    statement = fresh_rows(count_down_children(parent_id))
    result = await session.execute(statement)
    # Only the queued ones changed status; the others just count down.
    ready = [job for job in result.scalars() if job.status == JobStatus.QUEUED]
    record_changes(session, ready)
    return ready


def count_down_children(parent_id: uuid.UUID) -> Update:
    """
    The UPDATE counting one more finished parent for each waiting
    child, queueing those with none left. One statement: every SET
    expression reads the old row, so ``pending_parents = 1`` means
    "this parent was the last".

    :param parent_id: Job that just succeeded.
    :type parent_id: uuid.UUID
    :return: The statement.
    :rtype: Update
    """
    becomes_ready = Job.pending_parents == 1
    return (
        update(Job)
        .where(
            Job.id.in_(children_of(parent_id)),
            Job.status == JobStatus.WAITING,
        )
        .values(
            pending_parents=Job.pending_parents - 1,
            status=case((becomes_ready, JobStatus.QUEUED), else_=Job.status),
        )
    )


def children_of(job_id: uuid.UUID) -> Select:
    """
    The jobs directly downstream of one.

    :param job_id: The job.
    :type job_id: uuid.UUID
    :return: A query of child ids.
    :rtype: Select
    """
    return select(JobDependency.downstream_id).where(
        JobDependency.upstream_id == job_id
    )


def descendants_of(job_id: uuid.UUID) -> Select:
    """
    Every job downstream of one, found by a recursive query inside the
    database.

    :param job_id: The job.
    :type job_id: uuid.UUID
    :return: A query of descendant ids.
    :rtype: Select
    """
    edges = JobDependency.__table__
    found = (
        select(edges.c.downstream_id.label("id"))
        .where(edges.c.upstream_id == job_id)
        .cte("descendants", recursive=True)
    )
    found = found.union(
        select(edges.c.downstream_id).join(
            found, edges.c.upstream_id == found.c.id
        )
    )
    return select(found.c.id)


async def mark_descendants(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: JobStatus,
    message: str,
) -> list[uuid.UUID]:
    """
    Give every waiting descendant of a job the same final status.

    Descendants of a job that never succeeded are always still
    waiting, because each needs that job (directly or through others)
    to finish first.

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
    statement = (
        update(Job)
        .where(
            Job.id.in_(descendants_of(job_id)),
            Job.status == JobStatus.WAITING,
        )
        .values(status=status, error_message=message)
    )
    return [job.id for job in await update_jobs(session, statement)]


async def consequences(
    session: AsyncSession,
    job: Job,
    outcome: JobStatus,
) -> list[Job]:
    """
    What a job's end means for the jobs after it: success releases its
    children; failure or cancelling ends its descendants.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param job: The job that just ended.
    :type job: Job
    :param outcome: SUCCEEDED, FAILED or CANCELLED.
    :type outcome: JobStatus
    :return: Children that became queued.
    :rtype: list[Job]
    """
    if outcome is JobStatus.SUCCEEDED:
        return await release_children(session, job.id)
    status, message = DESCENDANT_STATUS[outcome]
    await mark_descendants(session, job.id, status, message)
    return []


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
    return Completion(job, await consequences(session, job, outcome))


async def requeue_lost(
    session: AsyncSession,
    job_id: uuid.UUID,
    attempt: int,
    limits: SilenceLimits,
) -> Job | None:
    """
    Put a job whose agent went silent back in the queue, clearing what
    belonged to the lost attempt.

    The heartbeat check is part of the same statement: if the agent
    reported in after the sweeper looked, nothing happens.

    :param session: Open database session; the caller commits and then
        dispatches the job.
    :type session: AsyncSession
    :param job_id: Job whose lease expired.
    :type job_id: uuid.UUID
    :param attempt: The attempt that was lost.
    :type attempt: int
    :param limits: Allowed silence, by kind of job.
    :type limits: SilenceLimits
    :return: The queued job, or None if it was not lost after all.
    :rtype: Job | None
    """
    return await transition(
        session,
        job_id,
        JobStatus.QUEUED,
        expected_attempt=attempt,
        extra_conditions=[lease_expired(limits)],
        **BETWEEN_ATTEMPTS,
    )


def lease_expired(limits: SilenceLimits) -> ColumnElement[bool]:
    """
    Condition: the job's agent has been silent longer than allowed for
    its kind of job.

    Uses the database clock, the same clock that stamped the heartbeat,
    so a skewed server clock cannot expire leases early.

    :param limits: Allowed silence for local and scheduled jobs.
    :type limits: SilenceLimits
    :return: SQL condition for use in a WHERE clause.
    :rtype: ColumnElement[bool]
    """
    allowed = case(
        (Job.scheduled, literal(limits.scheduled)), else_=literal(limits.local)
    )
    return Job.last_heartbeat_at < func.now() - allowed


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
    done = await complete_attempt(
        session,
        job_id,
        JobStatus.CANCELLED,
        extra_conditions=[Job.status.in_(NOT_STARTED_STATUSES)],
        error_message=CANCELLED_MESSAGE,
    )
    if done is not None:
        return JobStatus.CANCELLED
    flagged = await flag_cancel(session, Job.id == job_id)
    return JobStatus.RUNNING if flagged else None


async def cancel_run_jobs(
    session: AsyncSession, run_id: uuid.UUID
) -> RunCancel:
    """
    Cancel every unfinished job of a run: those not started at once,
    in one statement (so no job's cascade can hide another from the
    count), and running ones by asking their agents.

    :param session: Open database session; the caller commits with
        ``commit_and_publish``.
    :type session: AsyncSession
    :param run_id: The run.
    :type run_id: uuid.UUID
    :return: How many were cancelled, and how many are stopping.
    :rtype: RunCancel
    """
    statement = (
        update(Job)
        .where(Job.run_id == run_id, Job.status.in_(NOT_STARTED_STATUSES))
        .values(status=JobStatus.CANCELLED, error_message=CANCELLED_MESSAGE)
    )
    cancelled = await update_jobs(session, statement)
    flagged = await flag_cancel(session, Job.run_id == run_id)
    return RunCancel(cancelled=len(cancelled), cancelling=flagged)


async def flag_cancel(session: AsyncSession, which: ColumnElement[bool]) -> int:
    """
    Ask the agents running some jobs to stop them: their next
    heartbeat reply says so.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param which: Condition picking the jobs (one job, or a run's).
    :type which: ColumnElement[bool]
    :return: How many running jobs were flagged.
    :rtype: int
    """
    flagged = await session.execute(
        update(Job)
        .where(which, Job.status == JobStatus.RUNNING)
        .values(cancel_requested=True)
        .returning(Job.id)
    )
    return len(flagged.all())


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
    await queue.add_by_target((job.id, target_of[job.run_id]) for job in jobs)
