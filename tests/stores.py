"""
Helpers that create, reset and drop test-only stores.

Every destructive helper checks its target first: database names must
end in ``_test`` and Redis must not be database 0. One wrong
environment variable must never be able to wipe development data.
"""

import asyncpg
from redis.asyncio import Redis
from sqlalchemy.engine import make_url

from app.core.config import settings

TEST_DATABASE_SUFFIX = "_test"
MAINTENANCE_DATABASE = "postgres"
DEVELOPMENT_REDIS_DB = 0


def require_test_database() -> None:
    """
    Refuse to continue unless the configured database is test-only.

    :raises RuntimeError: If the name does not end in ``_test``.
    """
    if not settings.POSTGRES_DB.endswith(TEST_DATABASE_SUFFIX):
        raise RuntimeError(
            f"Refusing to reset database {settings.POSTGRES_DB!r}: "
            f"its name must end in {TEST_DATABASE_SUFFIX!r}"
        )


def require_test_redis() -> None:
    """
    Refuse to continue if Redis points at the development database.

    :raises RuntimeError: If ``REDIS_DB`` is 0.
    """
    if settings.REDIS_DB == DEVELOPMENT_REDIS_DB:
        raise RuntimeError("Refusing to flush Redis database 0")


def make_redis() -> Redis:
    """
    Open a Redis client on the test database, inside the caller's loop.

    :return: Client; the caller closes it with ``aclose()``.
    :rtype: Redis
    """
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )


async def execute_maintenance(statement: str) -> None:
    """
    Run one statement on the maintenance database.

    ``CREATE DATABASE`` and ``DROP DATABASE`` cannot run while connected
    to the database they act on.

    :param statement: SQL statement to execute.
    :type statement: str
    """
    maintenance_url = make_url(settings.database_url).set(
        drivername="postgresql",
        database=MAINTENANCE_DATABASE,
    )
    connection = await asyncpg.connect(
        maintenance_url.render_as_string(hide_password=False)
    )
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


async def drop_test_database() -> None:
    """
    Drop the configured test database, disconnecting its sessions.

    :raises RuntimeError: If the database is not test-only.
    """
    require_test_database()
    await execute_maintenance(
        f'DROP DATABASE IF EXISTS "{settings.POSTGRES_DB}" WITH (FORCE)'
    )


async def recreate_test_database() -> None:
    """
    Drop and recreate the configured test database, empty.

    :raises RuntimeError: If the database is not test-only.
    """
    await drop_test_database()
    await execute_maintenance(f'CREATE DATABASE "{settings.POSTGRES_DB}"')


async def flush_test_redis() -> None:
    """
    Empty the Redis database reserved for tests.

    :raises RuntimeError: If Redis points at database 0.
    """
    require_test_redis()
    redis_client = make_redis()
    try:
        await redis_client.flushdb()
    finally:
        await redis_client.aclose()


async def reset_test_stores() -> None:
    """
    Start a test session from an empty database and an empty Redis.

    :raises RuntimeError: If either store is not test-only.
    """
    await recreate_test_database()
    await flush_test_redis()
