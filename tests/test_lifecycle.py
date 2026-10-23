"""
Job lifecycle: each event is one transaction that also updates every
child, so a crash can never leave half a completion behind.
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.job import Job
from app.runs import lifecycle
from app.runs.lifecycle import (
    UPSTREAM_FAILED_MESSAGE,
    complete_attempt,
    start_attempt,
)
from app.runs.states import JobStatus
from app.runs.transitions import transition
from tests.graphs import build_graph, snapshot

# A feeds B and C; both feed D.
DIAMOND = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
WALLTIME = 10


async def run_and_finish(
    session: AsyncSession,
    job_id: uuid.UUID,
    outcome: JobStatus,
) -> lifecycle.Completion | None:
    """
    Start a job and finish it with ``outcome``, committing both.

    :param session: Open session.
    :type session: AsyncSession
    :param job_id: Job to run.
    :type job_id: uuid.UUID
    :param outcome: How it ends.
    :type outcome: JobStatus
    :return: The completion.
    :rtype: lifecycle.Completion | None
    """
    await start_attempt(session, job_id, WALLTIME)
    completion = await complete_attempt(session, job_id, outcome)
    await session.commit()
    return completion


def test_children_wait_for_every_parent(make_session: async_sessionmaker):
    """
    B and C start when A succeeds; D waits until both have succeeded.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, DIAMOND)
            after_a = await run_and_finish(
                session, ids["A"], JobStatus.SUCCEEDED
            )
            after_b = await run_and_finish(
                session, ids["B"], JobStatus.SUCCEEDED
            )
            waiting = await snapshot(session, ids)
            after_c = await run_and_finish(
                session, ids["C"], JobStatus.SUCCEEDED
            )
            return ids, after_a, after_b, waiting, after_c

    ids, after_a, after_b, waiting, after_c = asyncio.run(scenario())
    assert {job.id for job in after_a.ready} == {ids["B"], ids["C"]}
    assert after_b.ready == []
    assert waiting["D"] == (JobStatus.WAITING, 1)
    assert [job.id for job in after_c.ready] == [ids["D"]]


@pytest.mark.parametrize(
    ("outcome", "descendant_status"),
    [
        (JobStatus.FAILED, JobStatus.UPSTREAM_FAILED),
        (JobStatus.CANCELLED, JobStatus.CANCELLED),
    ],
)
def test_an_unsuccessful_job_ends_all_its_descendants(
    make_session: async_sessionmaker,
    outcome: JobStatus,
    descendant_status: JobStatus,
):
    """
    Failure (or cancellation) of A reaches B, C and, through them, D.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param outcome: How A ends.
    :type outcome: JobStatus
    :param descendant_status: What every descendant becomes.
    :type descendant_status: JobStatus
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, DIAMOND)
            await run_and_finish(session, ids["A"], outcome)
            failed_d = await session.get(Job, ids["D"])
            return await snapshot(session, ids), failed_d.error_message

    state, message = asyncio.run(scenario())
    assert state["A"][0] == outcome
    for name in "BCD":
        assert state[name][0] == descendant_status
    if outcome is JobStatus.FAILED:
        assert message == UPSTREAM_FAILED_MESSAGE


def test_a_duplicate_completion_counts_once(make_session: async_sessionmaker):
    """
    A second "done" for the same job changes nothing, so no child's
    parent count drops twice.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B"), ("Z", "B")])
            await run_and_finish(session, ids["A"], JobStatus.SUCCEEDED)
            again = await complete_attempt(
                session, ids["A"], JobStatus.SUCCEEDED
            )
            await session.commit()
            return again, await snapshot(session, ids)

    again, state = asyncio.run(scenario())
    assert again is None
    assert state["B"] == (JobStatus.WAITING, 1)


def test_a_stale_attempt_cannot_finish_the_job(
    make_session: async_sessionmaker,
):
    """
    After a retry, attempt 1's late report is ignored; attempt 2's
    counts.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(session, ids["A"], WALLTIME)
            await transition(session, ids["A"], JobStatus.QUEUED)  # retry
            await start_attempt(session, ids["A"], WALLTIME)
            stale = await complete_attempt(
                session, ids["A"], JobStatus.SUCCEEDED, expected_attempt=1
            )
            current = await complete_attempt(
                session, ids["A"], JobStatus.SUCCEEDED, expected_attempt=2
            )
            await session.commit()
            return stale, current

    stale, current = asyncio.run(scenario())
    assert stale is None
    assert current is not None
    assert current.job.attempt == 2


def test_a_crash_mid_completion_leaves_nothing_half_done(
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Fault test 2: if releasing the children fails, the parent's own
    "succeeded" is rolled back with it.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param monkeypatch: Makes the child update crash.
    :type monkeypatch: pytest.MonkeyPatch
    """

    async def crash(*args, **kwargs):
        raise RuntimeError("worker died mid-transaction")

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(session, ids["A"], WALLTIME)
            await session.commit()
        monkeypatch.setattr(lifecycle, "release_children", crash)
        with pytest.raises(RuntimeError):
            async with make_session() as session:
                await complete_attempt(session, ids["A"], JobStatus.SUCCEEDED)
                await session.commit()
        async with make_session() as session:
            return await snapshot(session, ids)

    state = asyncio.run(scenario())
    assert state["A"] == (JobStatus.RUNNING, 0)
    assert state["B"] == (JobStatus.WAITING, 1)
