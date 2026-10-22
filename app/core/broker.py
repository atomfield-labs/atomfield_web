"""
Redis broker connection settings shared by the API and the worker.
"""

from arq.connections import RedisSettings

from app.core.config import settings


def build_redis_settings() -> RedisSettings:
    """
    Build the one Redis connection description both processes use.

    Keeping it in one place means a new option (database, password)
    cannot reach the API but miss the worker.

    :return: Connection settings for ARQ pools and workers.
    :rtype: RedisSettings
    """
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )
