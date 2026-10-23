"""
Deliver job events to whoever is watching a run.

``EventBus`` is a protocol, so the code that publishes and the stream
that listens do not care how events travel. ``InMemoryEventBus`` works
inside one process (tests, a single API process); a Redis version
reaches every API process.

Delivery is best effort by contract: a bus never raises because a
message could not be delivered, and keeps nothing for late listeners.
A watcher that missed an event learns it from the stream's ping,
which carries the run's counter.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from app.events.models import JobEvent


class Subscription(Protocol):
    """
    A live feed of one run's events.
    """

    async def next_event(self, timeout_seconds: float) -> JobEvent | None:
        """
        Wait for the next event, but no longer than the timeout.

        A method with a timeout rather than an async iterator: the
        stream must stop waiting every few seconds to send a ping, and
        cancelling an async generator's pending step closes it for
        good.

        :param timeout_seconds: Longest wait.
        :type timeout_seconds: float
        :return: The event, or None if none arrived in time.
        :rtype: JobEvent | None
        """


class EventBus(Protocol):
    """
    Carries job events from the process that commits a change to the
    processes holding watchers' streams.
    """

    async def publish(self, events: Sequence[JobEvent]) -> None:
        """
        Hand events to everyone subscribed to their runs right now.

        :param events: Events to deliver, in order.
        :type events: Sequence[JobEvent]
        """

    def subscribe(
        self,
        run_id: uuid.UUID,
    ) -> AbstractAsyncContextManager[Subscription]:
        """
        Listen to one run for the duration of an ``async with`` block.

        Listening has started by the time the block is entered, so the
        caller can read the run's current state next without missing
        anything published in between.

        :param run_id: Run to watch.
        :type run_id: uuid.UUID
        :return: Context manager yielding the subscription.
        :rtype: AbstractAsyncContextManager[Subscription]
        """


class InMemorySubscription:
    """
    A subscription whose events wait in an asyncio queue.
    """

    def __init__(self) -> None:
        """
        Start with an empty inbox.
        """
        self.inbox: asyncio.Queue[JobEvent] = asyncio.Queue()

    async def next_event(self, timeout_seconds: float) -> JobEvent | None:
        """
        Wait for the next event, but no longer than the timeout.

        :param timeout_seconds: Longest wait.
        :type timeout_seconds: float
        :return: The event, or None if none arrived in time.
        :rtype: JobEvent | None
        """
        try:
            return await asyncio.wait_for(self.inbox.get(), timeout_seconds)
        except TimeoutError:
            return None


class InMemoryEventBus:
    """
    Event bus for listeners in the same process as the publisher.
    """

    def __init__(self) -> None:
        """
        Start with no listeners.
        """
        self.subscribers: defaultdict[uuid.UUID, set[InMemorySubscription]] = (
            defaultdict(set)
        )

    async def publish(self, events: Sequence[JobEvent]) -> None:
        """
        Put each event in the inbox of every listener of its run.

        :param events: Events to deliver, in order.
        :type events: Sequence[JobEvent]
        """
        for event in events:
            for subscription in self.subscribers.get(event.run_id, ()):
                subscription.inbox.put_nowait(event)

    @asynccontextmanager
    async def subscribe(
        self,
        run_id: uuid.UUID,
    ) -> AsyncIterator[InMemorySubscription]:
        """
        Listen to one run until the ``async with`` block ends.

        :param run_id: Run to watch.
        :type run_id: uuid.UUID
        :return: Context manager yielding the subscription.
        :rtype: AsyncIterator[InMemorySubscription]
        """
        subscription = InMemorySubscription()
        self.subscribers[run_id].add(subscription)
        try:
            yield subscription
        finally:
            listeners = self.subscribers[run_id]
            listeners.discard(subscription)
            if not listeners:
                del self.subscribers[run_id]
