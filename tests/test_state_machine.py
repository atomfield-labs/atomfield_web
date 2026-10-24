"""
The job state machine: the table of allowed moves, and conditional
updates that let exactly one of two racing writers win.
"""

import asyncio
import itertools
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.runs.lifecycle import create_run
from app.runs.states import (
    ALLOWED_SOURCES,
    FINAL_STATUSES,
    JobStatus,
    can_move,
)
from app.runs.transitions import transition
from tests.graphs import commit_changes


async def insert_job(session: AsyncSession, status: JobStatus) -> uuid.UUID:
    """
    Store one job in its own run and commit it.

    :param session: Open session.
    :type session: AsyncSession
    :param status: Starting status.
    :type status: JobStatus
    :return: The job's id.
    :rtype: uuid.UUID
    """
    run = await create_run(session, None, f"test_{uuid.uuid4().hex[:8]}")
    job = Job(
        run_id=run.id, script_name="toy_opt", node_key="opt", status=status
    )
    session.add(job)
    await commit_changes(session)
    return job.id


@pytest.mark.parametrize(
    ("source", "target"),
    list(itertools.product(JobStatus, JobStatus)),
)
def test_moves_follow_the_table(source: JobStatus, target: JobStatus):
    """
    Every pair of states is allowed exactly when the table says so.

    :param source: Current status.
    :type source: JobStatus
    :param target: Wanted status.
    :type target: JobStatus
    """
    expected = source in ALLOWED_SOURCES.get(target, frozenset())
    assert can_move(source, target) is expected


def test_finished_jobs_never_move():
    """
    No allowed move starts from a final status.
    """
    for sources in ALLOWED_SOURCES.values():
        assert sources.isdisjoint(FINAL_STATUSES)


def test_allowed_move_updates_and_returns_the_job(make_session):
    """
    A queued job can be claimed; the new values are written with it.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario() -> Job | None:
        async with make_session() as session:
            job_id = await insert_job(session, JobStatus.QUEUED)
            moved = await transition(
                session, job_id, JobStatus.RUNNING, attempt=1
            )
            await commit_changes(session)
            return moved

    moved = asyncio.run(scenario())
    assert moved is not None
    assert moved.status == JobStatus.RUNNING
    assert moved.attempt == 1


def test_forbidden_move_changes_nothing(make_session):
    """
    A finished job cannot be claimed again.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario() -> tuple[Job | None, str]:
        async with make_session() as session:
            job_id = await insert_job(session, JobStatus.SUCCEEDED)
            moved = await transition(session, job_id, JobStatus.RUNNING)
            await commit_changes(session)
            job = await session.get(Job, job_id, populate_existing=True)
            return moved, job.status

    moved, status = asyncio.run(scenario())
    assert moved is None
    assert status == JobStatus.SUCCEEDED


def test_two_racing_claims_have_one_winner(make_session):
    """
    Two sessions claim the same job at once: Postgres makes the second
    wait for the first to commit, re-checks its WHERE clause, and finds
    nothing to update.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def claim(job_id: uuid.UUID, agent: int) -> bool:
        async with make_session() as session:
            moved = await transition(
                session, job_id, JobStatus.RUNNING, attempt=agent
            )
            await asyncio.sleep(0.05)  # hold the row lock a moment
            await commit_changes(session)
            return moved is not None

    async def scenario() -> list[bool]:
        async with make_session() as session:
            job_id = await insert_job(session, JobStatus.QUEUED)
        return await asyncio.gather(claim(job_id, 1), claim(job_id, 2))

    assert sorted(asyncio.run(scenario())) == [False, True]


def test_report_from_an_old_attempt_is_ignored(make_session):
    """
    With ``expected_attempt``, a stale attempt cannot finish the job.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario() -> tuple[Job | None, Job | None]:
        async with make_session() as session:
            job_id = await insert_job(session, JobStatus.QUEUED)
            await transition(session, job_id, JobStatus.RUNNING, attempt=2)
            stale = await transition(
                session, job_id, JobStatus.SUCCEEDED, expected_attempt=1
            )
            current = await transition(
                session, job_id, JobStatus.SUCCEEDED, expected_attempt=2
            )
            await commit_changes(session)
            return stale, current

    stale, current = asyncio.run(scenario())
    assert stale is None
    assert current is not None
