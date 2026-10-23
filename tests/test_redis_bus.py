"""
The Redis event bus: events cross between separate connections (as
between two API processes), and Redis trouble never fails a publish.
"""

import asyncio
import uuid

import pytest
from redis.asyncio import Redis

from app.events.models import JobEvent
from app.events.redis_bus import RedisEventBus, channel_name
from app.runs.states import JobStatus
from tests.stores import make_redis

# Nothing listens on port 1: connecting fails at once.
UNREACHABLE = {"host": "127.0.0.1", "port": 1}


def event_for(run_id: uuid.UUID, seq: int = 1) -> JobEvent:
    """
    A small event for ``run_id``.

    :param run_id: Run the event belongs to.
    :type run_id: uuid.UUID
    :param seq: Its number.
    :type seq: int
    :return: Event.
    :rtype: JobEvent
    """
    return JobEvent(
        run_id=run_id,
        seq=seq,
        job_id=uuid.uuid4(),
        status=JobStatus.RUNNING,
        attempt=1,
    )


def test_an_event_reaches_a_listener_on_another_connection():
    """
    Two clients stand in for two API processes: every event published
    right after subscribing arrives, in order.
    """

    async def scenario():
        publisher, listener = make_redis(), make_redis()
        try:
            run_id = uuid.uuid4()
            sent = [event_for(run_id, seq) for seq in (1, 2, 3)]
            async with RedisEventBus(listener).subscribe(run_id) as feed:
                await RedisEventBus(publisher).publish(sent)
                heard = [await feed.next_event(1.0) for _ in sent]
            return sent, heard
        finally:
            await publisher.aclose()
            await listener.aclose()

    sent, heard = asyncio.run(scenario())
    assert heard == sent


class UnconfirmedPubSub:
    """
    A connection whose subscription Redis never confirms.
    """

    async def subscribe(self, channel: str) -> None:
        """
        Pretend to send the request.

        :param channel: Channel name.
        :type channel: str
        """

    async def get_message(self, timeout: float) -> None:
        """
        Wait, and receive nothing.

        :param timeout: Longest wait.
        :type timeout: float
        """
        await asyncio.sleep(timeout)

    async def aclose(self) -> None:
        """
        Nothing to close.
        """


class UnconfirmedRedis:
    """
    A Redis client whose subscriptions are never confirmed.
    """

    def pubsub(self) -> UnconfirmedPubSub:
        """
        Open a connection that never confirms.

        :return: The connection.
        :rtype: UnconfirmedPubSub
        """
        return UnconfirmedPubSub()


def test_subscribing_waits_for_redis_to_confirm():
    """
    Until Redis confirms, a publish could miss this listener, so the
    block is never entered without a confirmation.
    """

    async def scenario():
        bus = RedisEventBus(UnconfirmedRedis(), confirm_seconds=0.05)
        async with bus.subscribe(uuid.uuid4()):
            pass

    with pytest.raises(TimeoutError):
        asyncio.run(scenario())


def test_a_publish_in_the_subscribe_gap_is_not_lost():
    """
    Publishing the instant the block is entered, many times over: the
    subscription is confirmed by Redis before the block starts, so no
    event can slip past.
    """

    async def once(bus: RedisEventBus) -> bool:
        run_id = uuid.uuid4()
        async with bus.subscribe(run_id) as feed:
            await bus.publish([event_for(run_id)])
            return await feed.next_event(1.0) is not None

    async def scenario():
        redis = make_redis()
        try:
            bus = RedisEventBus(redis)
            return [await once(bus) for _ in range(25)]
        finally:
            await redis.aclose()

    assert all(asyncio.run(scenario()))


def test_leaving_the_block_unsubscribes_and_silence_times_out():
    """
    No events: the wait returns None; afterwards Redis counts no
    listener left on the channel.
    """

    async def scenario():
        redis = make_redis()
        try:
            run_id = uuid.uuid4()
            async with RedisEventBus(redis).subscribe(run_id) as feed:
                silence = await feed.next_event(0.05)
            listeners = await redis.pubsub_numsub(channel_name(run_id))
            return silence, listeners[0][1]
        finally:
            await redis.aclose()

    assert asyncio.run(scenario()) == (None, 0)


def test_a_publish_with_redis_down_does_not_raise():
    """
    The change behind an event is already committed, so a failed
    publish is logged and the caller carries on.
    """

    async def scenario():
        redis = Redis(**UNREACHABLE)
        try:
            await RedisEventBus(redis).publish([event_for(uuid.uuid4())])
        finally:
            await redis.aclose()

    asyncio.run(scenario())
