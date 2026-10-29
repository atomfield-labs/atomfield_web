"""
Move a job between states with one conditional UPDATE.

``UPDATE ... WHERE id = :id AND status IN (:allowed) RETURNING`` is
check-and-set in a single statement: if two agents race to claim the
same job, the database lets exactly one of them change the row and the
other gets nothing back. No read-then-write gap exists to race in.

Every job UPDATE in the platform returns its rows through
``fresh_rows``, and those that change a status note it through
``update_jobs``, so the published changes always match the database.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Update, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.changes import record_changes
from app.models.job import Job
from app.runs.states import ALLOWED_SOURCES, JobStatus


def fresh_rows(statement: Update) -> Update:
    """
    A job UPDATE that returns the changed rows as Job objects, replacing
    any copy the session already loaded.

    :param statement: ``update(Job)`` with its conditions and values.
    :type statement: Update
    :return: The statement, returning the changed jobs.
    :rtype: Update
    """
    return statement.returning(Job).execution_options(
        synchronize_session=False, populate_existing=True
    )


async def update_jobs(session: AsyncSession, statement: Update) -> list[Job]:
    """
    Run a job UPDATE and note every job it changed, for publishing.

    :param session: Open database session; the caller commits with
        ``commit_and_publish``.
    :type session: AsyncSession
    :param statement: ``update(Job)`` with its conditions and values.
    :type statement: Update
    :return: The changed jobs.
    :rtype: list[Job]
    """
    jobs = list((await session.execute(fresh_rows(statement))).scalars())
    record_changes(session, jobs)
    return jobs


async def update_job(session: AsyncSession, statement: Update) -> Job | None:
    """
    Run an UPDATE of one job (``update_jobs``) and return it.

    :param session: Open database session; the caller commits with
        ``commit_and_publish``.
    :type session: AsyncSession
    :param statement: ``update(Job)`` matching at most one job.
    :type statement: Update
    :return: The changed job, or None if nothing matched.
    :rtype: Job | None
    """
    changed = await update_jobs(session, statement)
    return changed[0] if changed else None


def held_by(
    job_id: uuid.UUID, attempt: int, agent_id: uuid.UUID
) -> list[ColumnElement[bool]]:
    """
    Conditions: this attempt of the job runs, on this agent.

    :param job_id: The job.
    :type job_id: uuid.UUID
    :param attempt: The attempt.
    :type attempt: int
    :param agent_id: The agent's compute target.
    :type agent_id: uuid.UUID
    :return: SQL conditions for the WHERE clause.
    :rtype: list[ColumnElement[bool]]
    """
    return [
        Job.id == job_id,
        Job.status == JobStatus.RUNNING,
        Job.attempt == attempt,
        Job.agent_id == agent_id,
    ]


def move_conditions(
    job_id: uuid.UUID,
    target: JobStatus,
    expected_attempt: int | None,
    expected_agent: uuid.UUID | None,
) -> list[ColumnElement[bool]]:
    """
    The conditions under which one job may move to ``target``.

    :param job_id: Job to move.
    :type job_id: uuid.UUID
    :param target: Wanted status.
    :type target: JobStatus
    :param expected_attempt: Required attempt, if any.
    :type expected_attempt: int | None
    :param expected_agent: Required agent, if any.
    :type expected_agent: uuid.UUID | None
    :return: SQL conditions for the WHERE clause.
    :rtype: list[ColumnElement[bool]]
    """
    conditions = [Job.id == job_id, Job.status.in_(ALLOWED_SOURCES[target])]
    if expected_attempt is not None:
        conditions.append(Job.attempt == expected_attempt)
    if expected_agent is not None:
        conditions.append(Job.agent_id == expected_agent)
    return conditions


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
    conditions = move_conditions(
        job_id, target, expected_attempt, expected_agent
    )
    statement = (
        update(Job)
        .where(*conditions, *extra_conditions)
        .values(status=target, **values)
    )
    return await update_job(session, statement)
