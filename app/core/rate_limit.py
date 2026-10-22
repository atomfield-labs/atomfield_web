"""
Fixed-window rate limiting with a shared Redis counter.

Each (limit name, client) pair gets one counter per window. The counter
lives in Redis, not in process memory, so every API process enforces
the same total instead of each allowing its own share.
"""

from dataclasses import dataclass

from redis.asyncio import Redis

KEY_PREFIX = "ratelimit"


@dataclass(frozen=True, slots=True)
class RateLimit:
    """
    How many requests one client may make per window.

    :param name: Name of the limited action, part of the Redis key.
    :type name: str
    :param max_requests: Requests allowed per window.
    :type max_requests: int
    :param window_seconds: Window length in seconds.
    :type window_seconds: int
    """

    name: str
    max_requests: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateDecision:
    """
    Outcome of one rate-limit check.

    :param allowed: Whether the request may proceed.
    :type allowed: bool
    :param retry_after_seconds: Seconds until the window resets.
    :type retry_after_seconds: int
    """

    allowed: bool
    retry_after_seconds: int


class FixedWindowRateLimiter:
    """
    Counts requests per client in Redis and decides when to refuse.
    """

    def __init__(self, redis: Redis, limit: RateLimit) -> None:
        """
        Bind the limiter to a Redis connection and one limit.

        :param redis: Shared Redis client.
        :type redis: Redis
        :param limit: The limit to enforce.
        :type limit: RateLimit
        """
        self.redis = redis
        self.limit = limit

    async def check(self, client_id: str) -> RateDecision:
        """
        Count this request and decide whether it is within the limit.

        INCR, the first-time EXPIRE and TTL run in one transaction, so
        concurrent requests can neither skip a count nor leave a
        counter without an expiry.

        :param client_id: Who is making the request (e.g. an IP).
        :type client_id: str
        :return: Whether to allow it, and when to retry if not.
        :rtype: RateDecision
        """
        key = f"{KEY_PREFIX}:{self.limit.name}:{client_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self.limit.window_seconds, nx=True)
            pipe.ttl(key)
            count, _, ttl_seconds = await pipe.execute()
        allowed = count <= self.limit.max_requests
        return RateDecision(allowed, max(ttl_seconds, 0))
