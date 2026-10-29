"""
One Redis sorted set per compute target, holding queued job ids.

A sorted set (not a list) because it cannot hold the same member twice:
re-sending a job the queue already holds changes nothing, so the
sweeper can safely re-add every queued job on every pass.
"""

import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from redis.asyncio import Redis

QUEUE_KEY_PREFIX = "queue"


def queue_key(target_id: uuid.UUID) -> str:
    """
    Name the Redis key of one target's queue.

    :param target_id: Compute target.
    :type target_id: uuid.UUID
    :return: Key such as ``queue:<target id>``.
    :rtype: str
    """
    return f"{QUEUE_KEY_PREFIX}:{target_id}"


@dataclass(frozen=True, slots=True)
class QueuedJob:
    """
    A job taken off a queue, with the time it was first queued, which
    is its place in line.

    :param job_id: The job.
    :type job_id: uuid.UUID
    :param queued_at: Its score in the queue (seconds since the epoch).
    :type queued_at: float
    """

    job_id: uuid.UUID
    queued_at: float


class RedisJobQueue:
    """
    First-in, first-out delivery of job ids to each target's agents.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Use an existing Redis connection pool.

        :param redis: Shared async Redis client.
        :type redis: Redis
        """
        self.redis = redis

    async def add(
        self,
        target_id: uuid.UUID,
        job_ids: Iterable[uuid.UUID],
    ) -> int:
        """
        Queue jobs; a job already waiting keeps its original place.

        :param target_id: Compute target the jobs run on.
        :type target_id: uuid.UUID
        :param job_ids: Jobs to queue.
        :type job_ids: Iterable[uuid.UUID]
        :return: How many were not already queued.
        :rtype: int
        """
        now = time.time()
        members = {str(job_id): now for job_id in job_ids}
        if not members:
            return 0
        return await self.redis.zadd(queue_key(target_id), members, nx=True)

    async def take(
        self,
        target_id: uuid.UUID,
        timeout_seconds: float,
    ) -> QueuedJob | None:
        """
        Take the oldest job, waiting up to ``timeout_seconds`` for one.

        :param target_id: Compute target asking for work.
        :type target_id: uuid.UUID
        :param timeout_seconds: How long to wait; must be above zero
            (Redis treats zero as "wait forever").
        :type timeout_seconds: float
        :return: The job and its place in line, or None if none arrived
            in time.
        :rtype: QueuedJob | None
        """
        popped = await self.redis.bzpopmin(
            queue_key(target_id), timeout=timeout_seconds
        )
        if popped is None:
            return None
        _, member, score = popped
        text = member.decode() if isinstance(member, bytes) else member
        return QueuedJob(uuid.UUID(text), float(score))

    async def pop(
        self,
        target_id: uuid.UUID,
        timeout_seconds: float,
    ) -> uuid.UUID | None:
        """
        Take the oldest job's id, waiting up to ``timeout_seconds``.

        :param target_id: Compute target asking for work.
        :type target_id: uuid.UUID
        :param timeout_seconds: How long to wait; above zero.
        :type timeout_seconds: float
        :return: A job id, or None if none arrived in time.
        :rtype: uuid.UUID | None
        """
        taken = await self.take(target_id, timeout_seconds)
        return taken.job_id if taken else None

    async def put_back(self, target_id: uuid.UUID, taken: QueuedJob) -> None:
        """
        Return a taken job to its place in line, ahead of every job
        queued after it (a job already queued again stays as it is).

        :param target_id: Compute target it was taken for.
        :type target_id: uuid.UUID
        :param taken: The job, as ``take`` returned it.
        :type taken: QueuedJob
        """
        members = {str(taken.job_id): taken.queued_at}
        await self.redis.zadd(queue_key(target_id), members, nx=True)

    async def size(self, target_id: uuid.UUID) -> int:
        """
        Count the jobs waiting in one target's queue.

        :param target_id: Compute target.
        :type target_id: uuid.UUID
        :return: Number of queued job ids.
        :rtype: int
        """
        return await self.redis.zcard(queue_key(target_id))
