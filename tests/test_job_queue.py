"""
The Redis job queue: duplicates are harmless, order is first-in
first-out, and each compute target has its own queue.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.queue.job_queue import RedisJobQueue
from tests.stores import make_redis


def run_with_queue(scenario):
    """
    Run an async scenario with a queue on a fresh Redis connection.

    :param scenario: Coroutine function taking the queue.
    :type scenario: Callable[[RedisJobQueue], Awaitable]
    :return: Whatever the scenario returns.
    :rtype: Any
    """

    async def wrapper():
        redis = make_redis()
        try:
            return await scenario(RedisJobQueue(redis))
        finally:
            await redis.aclose()

    return asyncio.run(wrapper())


def test_adding_a_queued_job_again_changes_nothing(client: TestClient):
    """
    The sweeper re-adds every queued job; the queue must not grow.

    :param client: Ensures the test stores were reset.
    :type client: TestClient
    """
    target, job = uuid.uuid4(), uuid.uuid4()

    async def scenario(queue: RedisJobQueue):
        first = await queue.add(target, [job])
        second = await queue.add(target, [job])
        return first, second, await queue.size(target)

    assert run_with_queue(scenario) == (1, 0, 1)


def test_jobs_come_out_oldest_first(client: TestClient):
    """
    Pops return jobs in the order they were first queued.

    :param client: Ensures the test stores were reset.
    :type client: TestClient
    """
    target = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()

    async def scenario(queue: RedisJobQueue):
        await queue.add(target, [first])
        await asyncio.sleep(0.01)
        await queue.add(target, [second])
        return [await queue.pop(target, 0.1), await queue.pop(target, 0.1)]

    assert run_with_queue(scenario) == [first, second]


def test_an_empty_queue_times_out_and_targets_are_separate(
    client: TestClient,
):
    """
    A pop gives up after its timeout; a job for one target is never
    handed to another.

    :param client: Ensures the test stores were reset.
    :type client: TestClient
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()

    async def scenario(queue: RedisJobQueue):
        await queue.add(theirs, [uuid.uuid4()])
        return await queue.pop(mine, 0.1), await queue.size(theirs)

    assert run_with_queue(scenario) == (None, 1)
