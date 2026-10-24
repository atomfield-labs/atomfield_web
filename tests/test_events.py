"""
Job changes are numbered inside their transaction and announced after
commit: in commit order, never when rolled back, never forgotten.
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import InMemoryEventBus
from app.events.changes import UnpublishedChangesError, commit_and_publish
from app.events.models import JobEvent
from app.models.job import Job
from app.runs.lifecycle import complete_attempt, start_attempt
from app.runs.states import JobStatus
from tests.graphs import build_graph, run_counter

WALLTIME = 10


def described(
    events: list[JobEvent],
    ids: dict[str, uuid.UUID],
) -> list[tuple[str, str, int]]:
    """
    Turn events into (job name, status, number) for readable asserts.

    :param events: Events to describe.
    :type events: list[JobEvent]
    :param ids: Job name -> id.
    :type ids: dict[str, uuid.UUID]
    :return: One tuple per event, in order.
    :rtype: list[tuple[str, str, int]]
    """
    names = {job_id: name for name, job_id in ids.items()}
    return [(names[event.job_id], event.status, event.seq) for event in events]


def test_changes_are_numbered_in_the_order_they_commit(
    make_session: async_sessionmaker,
):
    """
    A watcher of the run sees A start, A finish and B become ready,
    numbered 1, 2, 3; the run's counter ends at 3.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        bus = InMemoryEventBus()
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            run_id = (await session.get(Job, ids["A"])).run_id
        async with bus.subscribe(run_id) as subscription:
            async with make_session() as session:
                await start_attempt(session, ids["A"], WALLTIME)
                await commit_and_publish(session, bus)
                await complete_attempt(session, ids["A"], JobStatus.SUCCEEDED)
                await commit_and_publish(session, bus)
                counter = await run_counter(session, ids["A"])
            seen = [await subscription.next_event(1.0) for _ in range(3)]
        return described(seen, ids), counter

    seen, counter = asyncio.run(scenario())
    assert seen == [
        ("A", JobStatus.RUNNING, 1),
        ("A", JobStatus.SUCCEEDED, 2),
        ("B", JobStatus.QUEUED, 3),
    ]
    assert counter == 3


def test_a_failure_announces_every_descendant(
    make_session: async_sessionmaker,
):
    """
    A fails: A, then its child and grandchild, in one numbered batch.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B"), ("B", "C")])
            await complete_attempt(session, ids["A"], JobStatus.FAILED)
            events = await commit_and_publish(session, InMemoryEventBus())
        return described(events, ids)

    first, *rest = asyncio.run(scenario())
    assert first == ("A", JobStatus.FAILED, 1)
    # One UPDATE marks both descendants; Postgres returns its rows in
    # no fixed order, so which of them gets 2 and which 3 may vary.
    assert sorted((name, status) for name, status, _ in rest) == [
        ("B", JobStatus.UPSTREAM_FAILED),
        ("C", JobStatus.UPSTREAM_FAILED),
    ]
    assert sorted(seq for *_, seq in rest) == [2, 3]


def test_only_the_final_state_of_a_job_is_announced(
    make_session: async_sessionmaker,
):
    """
    A job changed twice in one transaction yields one event: nobody
    could ever have seen the state in between.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(session, ids["A"], WALLTIME)
            await complete_attempt(session, ids["A"], JobStatus.SUCCEEDED)
            events = await commit_and_publish(session, InMemoryEventBus())
        return described(events, ids)

    assert asyncio.run(scenario()) == [
        ("A", JobStatus.SUCCEEDED, 1),
        ("B", JobStatus.QUEUED, 2),
    ]


def test_a_rolled_back_change_is_never_announced(
    make_session: async_sessionmaker,
):
    """
    Changes undone by a rollback leave no note behind: the next commit
    on the same session announces nothing and the counter stays at 0.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await complete_attempt(session, ids["A"], JobStatus.FAILED)
            await session.rollback()
            events = await commit_and_publish(session, InMemoryEventBus())
            return events, await run_counter(session, ids["A"])

    assert asyncio.run(scenario()) == ([], 0)


def test_a_plain_commit_of_job_changes_is_refused(
    make_session: async_sessionmaker,
):
    """
    Committing a change without numbering it raises, and nothing is
    saved: a forgotten ``commit_and_publish`` fails loudly in tests
    instead of leaving watchers silently out of date.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(session, ids["A"], WALLTIME)
            with pytest.raises(UnpublishedChangesError):
                await session.commit()
        async with make_session() as session:
            return (await session.get(Job, ids["A"])).status

    assert asyncio.run(scenario()) == JobStatus.QUEUED


def test_concurrent_changes_to_one_run_get_distinct_numbers(
    make_session: async_sessionmaker,
):
    """
    Two transactions start two jobs of the same run at once: the run's
    row lock makes them take turns, so their numbers never collide.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def start(job_id: uuid.UUID) -> list[JobEvent]:
        async with make_session() as session:
            await start_attempt(session, job_id, WALLTIME)
            await asyncio.sleep(0.05)  # both changes are in flight
            return await commit_and_publish(session, InMemoryEventBus())

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "C"), ("B", "C")])
        both = await asyncio.gather(start(ids["A"]), start(ids["B"]))
        return sorted(event.seq for events in both for event in events)

    assert asyncio.run(scenario()) == [1, 2]


def test_a_subscriber_hears_only_its_own_run():
    """
    Events for other runs are not delivered; an empty wait times out;
    leaving the block removes the listener.
    """

    def event_for(run_id: uuid.UUID) -> JobEvent:
        return JobEvent(
            run_id=run_id,
            seq=1,
            job_id=uuid.uuid4(),
            status=JobStatus.QUEUED,
            attempt=0,
        )

    async def scenario():
        bus = InMemoryEventBus()
        mine, other = uuid.uuid4(), uuid.uuid4()
        async with bus.subscribe(mine) as subscription:
            await bus.publish([event_for(other), event_for(mine)])
            heard = await subscription.next_event(1.0)
            silence = await subscription.next_event(0.05)
        return heard.run_id == mine, silence, dict(bus.subscribers)

    assert asyncio.run(scenario()) == (True, None, {})
