"""
Job events through Redis pub/sub, so a change committed by one API
process reaches watchers connected to any other.

Each run has a channel, ``run:<run id>``. A publish reaches every
connection subscribed to that channel at that moment; Redis keeps
nothing for later, which is why streams start with a snapshot and
check the run's counter at every ping.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

from app.events.models import JobEvent

logger = logging.getLogger(__name__)
CHANNEL_PREFIX = "run"
# Types of the messages a subscribed connection receives.
SUBSCRIBED = "subscribe"
PUBLISHED = "message"
CONFIRM_SECONDS = 5.0


def channel_name(run_id: uuid.UUID) -> str:
    """
    Name the Redis channel of one run.

    :param run_id: Run.
    :type run_id: uuid.UUID
    :return: Channel such as ``run:<run id>``.
    :rtype: str
    """
    return f"{CHANNEL_PREFIX}:{run_id}"


async def read_message(
    pubsub: PubSub,
    message_type: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    """
    Read messages until one of the wanted type arrives or time is up.

    :param pubsub: Subscribed connection.
    :type pubsub: PubSub
    :param message_type: ``SUBSCRIBED`` or ``PUBLISHED``.
    :type message_type: str
    :param timeout_seconds: Longest wait.
    :type timeout_seconds: float
    :return: The message, or None if none arrived in time.
    :rtype: dict[str, Any] | None
    """
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + timeout_seconds
    while (remaining := give_up_at - loop.time()) > 0:
        message = await pubsub.get_message(timeout=remaining)
        if message is not None and message["type"] == message_type:
            return message
    return None


class RedisSubscription:
    """
    One run's channel, on a Redis connection of its own.
    """

    def __init__(self, pubsub: PubSub) -> None:
        """
        Wrap a connection already subscribed to the run's channel.

        :param pubsub: Subscribed connection.
        :type pubsub: PubSub
        """
        self.pubsub = pubsub

    async def next_event(self, timeout_seconds: float) -> JobEvent | None:
        """
        Wait for the next event, but no longer than the timeout.

        :param timeout_seconds: Longest wait.
        :type timeout_seconds: float
        :return: The event, or None if none arrived in time.
        :rtype: JobEvent | None
        """
        message = await read_message(self.pubsub, PUBLISHED, timeout_seconds)
        if message is None:
            return None
        return JobEvent.model_validate_json(message["data"])


class RedisEventBus:
    """
    Event bus shared by every API process through Redis.
    """

    def __init__(
        self,
        redis: Redis,
        confirm_seconds: float = CONFIRM_SECONDS,
    ) -> None:
        """
        Use a Redis client for publishing and subscribing.

        :param redis: Shared client; each subscription takes one of its
            pool's connections for as long as it lasts.
        :type redis: Redis
        :param confirm_seconds: How long to wait for Redis to confirm a
            subscription.
        :type confirm_seconds: float
        """
        self.redis = redis
        self.confirm_seconds = confirm_seconds

    async def publish(self, events: Sequence[JobEvent]) -> None:
        """
        Publish events in one round trip, in order.

        A Redis failure is logged, not raised: the change is already
        committed, so failing the request would only make its sender
        retry something that succeeded. Watchers catch up at their
        stream's next ping.

        :param events: Events to deliver, in order.
        :type events: Sequence[JobEvent]
        """
        if not events:
            return
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for event in events:
                    channel = channel_name(event.run_id)
                    pipe.publish(channel, event.model_dump_json())
                await pipe.execute()
        except RedisError:
            logger.warning(
                "Could not publish %d job events; watchers will catch up",
                len(events),
                exc_info=True,
            )

    @asynccontextmanager
    async def subscribe(
        self,
        run_id: uuid.UUID,
    ) -> AsyncIterator[RedisSubscription]:
        """
        Listen to one run until the ``async with`` block ends.

        ``PubSub.subscribe`` only sends the request; until Redis has
        handled it, a publish from another connection would not reach
        this one. Waiting for the confirmation keeps the promise that
        listening has started once the block is entered.

        :param run_id: Run to watch.
        :type run_id: uuid.UUID
        :return: Context manager yielding the subscription.
        :rtype: AsyncIterator[RedisSubscription]
        :raises TimeoutError: If Redis does not confirm in time.
        """
        pubsub = self.redis.pubsub()
        try:
            await pubsub.subscribe(channel_name(run_id))
            confirmed = await read_message(
                pubsub, SUBSCRIBED, self.confirm_seconds
            )
            if confirmed is None:
                raise TimeoutError("Redis did not confirm the subscription")
            yield RedisSubscription(pubsub)
        finally:
            await pubsub.aclose()
