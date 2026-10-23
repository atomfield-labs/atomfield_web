"""
One watcher's live view of a run, as server-sent events (SSE): a
response that never ends, into which the server writes a short text
frame whenever there is news.

Order matters: subscribe first, then read the snapshot. Anything
published while the snapshot is read waits in the subscription, and
events the snapshot already includes (numbered at or below its
counter) are dropped.

Every ``ping_seconds`` the stream reads the run's counter. If it is
ahead of every number the stream has seen, an event was lost (a crash
between commit and publish, or Redis trouble), so the stream sends a
fresh snapshot instead of a ping. The browser never checks for gaps.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import EventBus, Subscription
from app.events.models import JobState, RunSnapshot
from app.models.job import Job
from app.models.run import Run

SNAPSHOT_EVENT = "snapshot"
JOB_EVENT = "job"
PING_EVENT = "ping"
PING_SECONDS = 15.0


def sse_frame(event_name: str, data: str) -> str:
    """
    Format one SSE frame.

    :param event_name: Frame type the browser dispatches on.
    :type event_name: str
    :param data: One line of JSON.
    :type data: str
    :return: The frame, ending in the blank line that closes it.
    :rtype: str
    """
    return f"event: {event_name}\ndata: {data}\n\n"


async def read_snapshot(
    session_factory: async_sessionmaker,
    run_id: uuid.UUID,
) -> RunSnapshot | None:
    """
    Read the run's counter and all its jobs in one SQL statement, so
    both come from the same moment.

    :param session_factory: Creates a short-lived session.
    :type session_factory: async_sessionmaker
    :param run_id: Run to read.
    :type run_id: uuid.UUID
    :return: The snapshot, or None if the run no longer exists.
    :rtype: RunSnapshot | None
    """
    query = (
        select(
            Run.event_seq, Job.id, Job.status, Job.attempt, Job.error_message
        )
        .select_from(Run)
        .outerjoin(Job, Job.run_id == Run.id)
        .where(Run.id == run_id)
        .order_by(Job.created_at)
    )
    async with session_factory() as session:
        rows = (await session.execute(query)).all()
    if not rows:
        return None
    jobs = [
        JobState(
            job_id=job_id, status=status, attempt=attempt, error_message=error
        )
        for _, job_id, status, attempt, error in rows
        if job_id is not None
    ]
    return RunSnapshot(run_id=run_id, seq=rows[0].event_seq, jobs=jobs)


async def read_counter(
    session_factory: async_sessionmaker,
    run_id: uuid.UUID,
) -> int | None:
    """
    Read how many changes the run has announced.

    :param session_factory: Creates a short-lived session.
    :type session_factory: async_sessionmaker
    :param run_id: Run to read.
    :type run_id: uuid.UUID
    :return: The counter, or None if the run no longer exists.
    :rtype: int | None
    """
    query = select(Run.event_seq).where(Run.id == run_id)
    async with session_factory() as session:
        return (await session.execute(query)).scalar_one_or_none()


class RunStream:
    """
    Produces the frames of one watcher's stream of one run.
    """

    def __init__(
        self,
        run_id: uuid.UUID,
        session_factory: async_sessionmaker,
        bus: EventBus,
        ping_seconds: float = PING_SECONDS,
    ) -> None:
        """
        Prepare a stream; nothing is read until ``frames`` starts.

        :param run_id: Run to watch.
        :type run_id: uuid.UUID
        :param session_factory: Creates short-lived sessions. A stream
            can last hours, so it never holds a connection between
            reads.
        :type session_factory: async_sessionmaker
        :param bus: Where events arrive.
        :type bus: EventBus
        :param ping_seconds: Time between pings.
        :type ping_seconds: float
        """
        self.run_id = run_id
        self.session_factory = session_factory
        self.bus = bus
        self.ping_seconds = ping_seconds
        # Events at or below this are in the last snapshot sent.
        self.snapshot_seq = 0
        # Highest number the watcher has been given, in any frame.
        self.highest_seq = 0
        self.ping_due = 0.0

    async def frames(self) -> AsyncIterator[str]:
        """
        Yield a snapshot, then events, pings and repair snapshots,
        until the run is deleted or the watcher disconnects.

        :return: SSE frames.
        :rtype: AsyncIterator[str]
        """
        async with self.bus.subscribe(self.run_id) as subscription:
            frame = await self.snapshot_frame()
            while frame is not None:
                yield frame
                frame = await self.next_frame(subscription)

    async def snapshot_frame(self) -> str | None:
        """
        Read and format a snapshot; it resets the numbers and the ping
        timer.

        :return: The frame, or None if the run no longer exists.
        :rtype: str | None
        """
        snapshot = await read_snapshot(self.session_factory, self.run_id)
        if snapshot is None:
            return None
        self.snapshot_seq = self.highest_seq = snapshot.seq
        self.ping_due = asyncio.get_running_loop().time() + self.ping_seconds
        return sse_frame(SNAPSHOT_EVENT, snapshot.model_dump_json())

    async def next_frame(self, subscription: Subscription) -> str | None:
        """
        Wait for an event newer than the snapshot; when the ping is
        due first, send a ping (or a repair snapshot) instead.

        Events newer than the snapshot are passed on even when they
        arrive out of order: they may be about different jobs, and the
        browser keeps the highest number per job.

        :param subscription: The run's live feed.
        :type subscription: Subscription
        :return: The next frame, or None if the run no longer exists.
        :rtype: str | None
        """
        loop = asyncio.get_running_loop()
        while (wait := self.ping_due - loop.time()) > 0:
            event = await subscription.next_event(wait)
            if event is not None and event.seq > self.snapshot_seq:
                self.highest_seq = max(self.highest_seq, event.seq)
                return sse_frame(JOB_EVENT, event.model_dump_json())
        return await self.ping_frame()

    async def ping_frame(self) -> str | None:
        """
        Compare the run's counter with what the watcher has: equal
        means nothing was missed (send a ping); ahead means an event
        was lost (send a fresh snapshot).

        :return: The frame, or None if the run no longer exists.
        :rtype: str | None
        """
        counter = await read_counter(self.session_factory, self.run_id)
        if counter is None:
            return None
        if counter > self.highest_seq:
            return await self.snapshot_frame()
        self.ping_due = asyncio.get_running_loop().time() + self.ping_seconds
        return sse_frame(PING_EVENT, json.dumps({"seq": counter}))
