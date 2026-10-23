"""
The Redis connection shared by the API's queue, rate limits and sweeper.
"""

from redis.asyncio import Redis

from app.core.config import settings


def create_redis() -> Redis:
    """
    Open the one Redis client the API process uses.

    Keeping the connection options in one place means a new one (a
    password, a database number) cannot reach one caller but miss
    another.

    :return: Client with its own connection pool; close with
        ``aclose()``.
    :rtype: Redis
    """
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )
