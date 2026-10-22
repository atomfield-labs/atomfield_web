"""
Alembic environment: runs migrations with the application's settings.

The URL comes from ``settings.database_url``, not ``alembic.ini``, so
there is one source of truth and the password never passes through
configparser, which treats ``%`` as special.
"""

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from alembic.runtime.migration import MigrationContext
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    # Keep the application's loggers alive when migrating in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
logger = logging.getLogger("alembic.env")

ALLOW_DOWNGRADE_VARIABLE = "ALLOW_DOWNGRADE"
# Name of the step function alembic.command.downgrade hands to env.py.
DOWNGRADE_FUNCTION = "downgrade"


def run_migrations_offline() -> None:
    """
    Emit migration SQL to stdout without connecting (``--sql`` mode).
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def require_downgrade_permission(migration_context: MigrationContext) -> None:
    """
    Refuse a downgrade unless ``ALLOW_DOWNGRADE=1`` is set.

    A downgrade drops tables and their data. An explicit opt-in turns
    "which database is this?" into a decision instead of a default.

    :param migration_context: Context of the command being run.
    :type migration_context: MigrationContext
    :raises RuntimeError: If this is a downgrade without the opt-in.
    """
    migration_fn = migration_context.opts.get("fn")
    if migration_fn is None or migration_fn.__name__ != DOWNGRADE_FUNCTION:
        return
    if os.environ.get(ALLOW_DOWNGRADE_VARIABLE) == "1":
        return
    raise RuntimeError(
        f"Refusing to downgrade database {settings.POSTGRES_DB!r} on "
        f"{settings.POSTGRES_HOST}: downgrades drop data. Set "
        f"{ALLOW_DOWNGRADE_VARIABLE}=1 to confirm."
    )


def do_run_migrations(connection: Connection) -> None:
    """
    Run pending migrations on an open synchronous connection.

    :param connection: Connection handed over by ``run_sync``.
    :type connection: Connection
    :raises RuntimeError: If this is a downgrade without the opt-in.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    require_downgrade_permission(context.get_context())
    logger.info(
        "Database %r on %s",
        settings.POSTGRES_DB,
        settings.POSTGRES_HOST,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Open an async engine and run the migrations through it.

    ``NullPool`` because this engine lives for one command only.
    """
    engine = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """
    Run migrations against the live database.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
