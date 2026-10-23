"""
A run's event stream: snapshot first, then newer events; old events
dropped; a lost event repaired by a fresh snapshot at the next ping.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import InMemoryEventBus, InMemorySubscription
from app.events.changes import commit_and_publish
from app.events.models import JobEvent
from app.events.stream import RunStream
from app.models.job import Job
from app.models.run import Run
from app.runs.lifecycle import start_attempt
from app.runs.states import JobStatus
from tests.graphs import build_graph

UserHeadersFactory = Callable[..., dict[str, str]]
PING_SECONDS = 0.2
WALLTIME = 10


def parse(frame: str) -> tuple[str, dict]:
    """
    Split an SSE frame into its type and its JSON data.

    :param frame: ``event: <type>\\ndata: <json>\\n\\n``.
    :type frame: str
    :return: (type, data).
    :rtype: tuple[str, dict]
    """
    event_line, data_line, *_ = frame.split("\n")
    return (
        event_line.removeprefix("event: "),
        json.loads(data_line.removeprefix("data: ")),
    )


def statuses(snapshot: dict, ids: dict[str, uuid.UUID]) -> dict[str, str]:
    """
    Read a snapshot's job statuses by job name.

    :param snapshot: Snapshot frame data.
    :type snapshot: dict
    :param ids: Job name -> id.
    :type ids: dict[str, uuid.UUID]
    :return: Name -> status.
    :rtype: dict[str, str]
    """
    names = {str(job_id): name for name, job_id in ids.items()}
    return {names[job["job_id"]]: job["status"] for job in snapshot["jobs"]}


async def start_job(
    make_session: async_sessionmaker,
    job_id: uuid.UUID,
    bus: InMemoryEventBus,
) -> list[JobEvent]:
    """
    Start a job and announce it on ``bus``.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param job_id: Job to start.
    :type job_id: uuid.UUID
    :param bus: Where the change is published.
    :type bus: InMemoryEventBus
    :return: The published events.
    :rtype: list[JobEvent]
    """
    async with make_session() as session:
        await start_attempt(session, job_id, WALLTIME)
        return await commit_and_publish(session, bus)


def watch(make_session: async_sessionmaker, scenario):
    """
    Run ``scenario(frames, bus, ids, run_id)`` against the stream of a
    fresh A -> B run, closing the stream afterwards.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param scenario: Coroutine function driving the stream.
    :type scenario: Callable
    :return: Whatever the scenario returns.
    :rtype: Any
    """

    async def wrapper():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            run_id = (await session.get(Job, ids["A"])).run_id
        bus = InMemoryEventBus()
        stream = RunStream(run_id, make_session, bus, PING_SECONDS)
        frames = stream.frames()
        try:
            return await scenario(frames, bus, ids, run_id)
        finally:
            await frames.aclose()

    return asyncio.run(wrapper())


def test_a_snapshot_comes_first_then_each_change(make_session):
    """
    The watcher first gets every job's state and the counter, then the
    change made after it connected.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(frames, bus, ids, run_id):
        first = parse(await anext(frames))
        await start_job(make_session, ids["A"], bus)
        second = parse(await anext(frames))
        return ids, first, second

    ids, (kind, snapshot), (change_kind, change) = watch(make_session, scenario)
    assert kind == "snapshot"
    assert snapshot["seq"] == 0
    assert statuses(snapshot, ids) == {"A": "queued", "B": "waiting"}
    assert change_kind == "job"
    assert change["job_id"] == str(ids["A"])
    assert (change["status"], change["seq"]) == (JobStatus.RUNNING, 1)


class RacingBus(InMemoryEventBus):
    """
    A bus where a job changes just before each subscription starts
    listening: the change's event is published to nobody.
    """

    def __init__(self, change: Callable[[], Awaitable[object]]) -> None:
        """
        Remember the change to make.

        :param change: Makes and announces the racing change.
        :type change: Callable[[], Awaitable[object]]
        """
        super().__init__()
        self.change = change

    @asynccontextmanager
    async def subscribe(
        self,
        run_id: uuid.UUID,
    ) -> AsyncIterator[InMemorySubscription]:
        """
        Make the racing change, then start listening.

        :param run_id: Run to watch.
        :type run_id: uuid.UUID
        :return: Context manager yielding the subscription.
        :rtype: AsyncIterator[InMemorySubscription]
        """
        await self.change()
        async with super().subscribe(run_id) as subscription:
            yield subscription


def test_a_change_racing_the_subscription_is_in_the_snapshot(
    make_session: async_sessionmaker,
):
    """
    The checkpoint question: the stream subscribes before reading the
    snapshot, so a change published to nobody just before listening
    began is already in the first snapshot. (Snapshot first would show
    A still queued until the next ping.)

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            run_id = (await session.get(Job, ids["A"])).run_id
        bus = RacingBus(
            lambda: start_job(make_session, ids["A"], InMemoryEventBus())
        )
        frames = RunStream(run_id, make_session, bus, PING_SECONDS).frames()
        try:
            return ids, parse(await anext(frames))
        finally:
            await frames.aclose()

    ids, (kind, snapshot) = asyncio.run(scenario())
    assert kind == "snapshot"
    assert statuses(snapshot, ids)["A"] == "running"


def test_an_event_the_snapshot_includes_is_dropped(make_session):
    """
    A late copy of an event already counted in the snapshot is not
    sent; with nothing else happening, a ping follows.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(frames, bus, ids, run_id):
        late = await start_job(make_session, ids["A"], InMemoryEventBus())
        snapshot = parse(await anext(frames))
        await bus.publish(late)
        return snapshot, parse(await anext(frames))

    (_, snapshot), following = watch(make_session, scenario)
    assert snapshot["seq"] == 1
    assert following == ("ping", {"seq": 1})


def test_a_lost_event_is_repaired_at_the_next_ping(make_session):
    """
    Fault test: a change whose event never reaches the stream (as if
    the process died between commit and publish). At the ping the
    counter is ahead, so a fresh snapshot is sent instead.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(frames, bus, ids, run_id):
        await anext(frames)
        await start_job(make_session, ids["A"], InMemoryEventBus())
        return ids, parse(await anext(frames))

    ids, (kind, repair) = watch(make_session, scenario)
    assert kind == "snapshot"
    assert repair["seq"] == 1
    assert statuses(repair, ids)["A"] == "running"


def test_the_stream_ends_when_the_run_is_deleted(make_session):
    """
    Once the run is gone, the next ping ends the stream instead of
    pinging forever.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(frames, bus, ids, run_id):
        await anext(frames)
        async with make_session() as session:
            await session.execute(delete(Run).where(Run.id == run_id))
            await session.commit()
        return [frame async for frame in frames]

    assert watch(make_session, scenario) == []


def test_only_the_owner_may_watch_a_run(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    No key: 401. Someone else's run: 404, as if it did not exist.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner, stranger = make_user_headers(), make_user_headers()
    payload = {
        "nodes": [{"ui_id": "only", "script_name": "toy_opt"}],
        "edges": [],
    }
    run_id = client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=owner
    ).json()["run_id"]
    url = f"/api/runs/{run_id}/events"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=stranger).status_code == 404
