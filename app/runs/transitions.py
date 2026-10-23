"""
Move a job between states with one conditional UPDATE.

``UPDATE ... WHERE id = :id AND status IN (:allowed) RETURNING`` is
check-and-set in a single statement: if two agents race to claim the
same job, the database lets exactly one of them change the row and the
other gets nothing back. No read-then-write gap exists to race in.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.changes import record_changes
from app.models.job import Job
from app.runs.states import ALLOWED_SOURCES, JobStatus


async def transition(
    session: AsyncSession,
    job_id: uuid.UUID,
    target: JobStatus,
    expected_attempt: int | None = None,
    expected_agent: uuid.UUID | None = None,
    extra_conditions: Sequence[ColumnElement[bool]] = (),
    **values: Any,
) -> Job | None:
    """
    Move one job to ``target`` if the table allows it from its status.

    Runs inside the caller's transaction; the caller commits with
    ``commit_and_publish``, which announces the change.

    :param session: Open database session.
    :type session: AsyncSession
    :param job_id: Job to move.
    :type job_id: uuid.UUID
    :param target: Wanted status.
    :type target: JobStatus
    :param expected_attempt: If given, move only if the job is still on
        this attempt; a report from an older attempt changes nothing.
    :type expected_attempt: int | None
    :param expected_agent: If given, move only if this agent holds the
        job. Attempt numbers are small and guessable, so they alone
        cannot stop one agent from finishing another's job.
    :type expected_agent: uuid.UUID | None
    :param extra_conditions: More conditions the row must meet, checked
        in the same statement (e.g. "heartbeat still stale").
    :type extra_conditions: Sequence[ColumnElement[bool]]
    :param values: Other columns to set in the same statement.
    :type values: Any
    :return: The updated job, or None if the move did not happen.
    :rtype: Job | None
    """
    conditions = [
        Job.id == job_id,
        Job.status.in_(ALLOWED_SOURCES[target]),
        *extra_conditions,
    ]
    if expected_attempt is not None:
        conditions.append(Job.attempt == expected_attempt)
    if expected_agent is not None:
        conditions.append(Job.agent_id == expected_agent)
    statement = (
        update(Job)
        .where(*conditions)
        .values(status=target, **values)
        .returning(Job)
        # The returned row replaces any copy this session already loaded.
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    job = (await session.execute(statement)).scalars().first()
    if job is not None:
        record_changes(session, [job])
    return job
