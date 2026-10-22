"""
Bring the database schema up to the latest migration.

Run before the API starts: ``python -m app.db.migrate``.

1. A database created by the old ``create_all`` startup has the baseline
   tables but no Alembic history. It is stamped at the baseline first
   ("adopted"), so the baseline does not recreate existing tables.
2. If migrations are pending on a database that holds tables, a
   ``pg_dump`` backup is taken first.
3. Pending migrations are applied.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.db.backup import create_backup, prune_backups

logger = logging.getLogger(__name__)

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
BASELINE_REVISION = "0001"
HEAD_REVISION = "head"
VERSION_TABLE = "alembic_version"
BASELINE_TABLES = frozenset({"api_keys", "jobs", "job_dependencies"})


@dataclass(frozen=True, slots=True)
class DatabaseState:
    """
    What the database holds before migrating.

    :param tables: Names of the tables present.
    :type tables: frozenset[str]
    :param revision: Applied Alembic revision, or None if never stamped.
    :type revision: str | None
    """

    tables: frozenset[str]
    revision: str | None


def read_database_state(sync_connection: Connection) -> DatabaseState:
    """
    Read tables and revision; both readers need a sync connection.

    :param sync_connection: Connection handed over by ``run_sync``.
    :type sync_connection: Connection
    :return: Snapshot of the database before migrating.
    :rtype: DatabaseState
    """
    tables = frozenset(inspect(sync_connection).get_table_names())
    migration_context = MigrationContext.configure(sync_connection)
    return DatabaseState(tables, migration_context.get_current_revision())


async def inspect_database() -> DatabaseState:
    """
    Connect once and snapshot the database state.

    :return: Snapshot of the database before migrating.
    :rtype: DatabaseState
    """
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(read_database_state)
    finally:
        await engine.dispose()


def needs_adoption(table_names: set[str] | frozenset[str]) -> bool:
    """
    Decide whether the database predates Alembic.

    :param table_names: Tables currently in the database.
    :type table_names: set[str] | frozenset[str]
    :return: True if the baseline tables exist without any history.
    :rtype: bool
    """
    has_history = VERSION_TABLE in table_names
    return not has_history and BASELINE_TABLES <= table_names


def needs_backup(state: DatabaseState, head_revision: str) -> bool:
    """
    Back up only when something would change data that already exists.

    :param state: Database snapshot, after any adoption.
    :type state: DatabaseState
    :param head_revision: Latest revision in ``migrations/``.
    :type head_revision: str
    :return: True if migrations are pending on a non-empty database.
    :rtype: bool
    """
    holds_data = bool(state.tables - {VERSION_TABLE})
    return holds_data and state.revision != head_revision


def build_alembic_config() -> Config:
    """
    Load the project's Alembic configuration.

    :return: Configuration pointing at ``migrations/``.
    :rtype: Config
    """
    return Config(str(ALEMBIC_INI))


def back_up_before_migrating() -> None:
    """
    Take a backup and drop the oldest ones, unless explicitly skipped.
    """
    if settings.SKIP_DB_BACKUP:
        logger.warning("SKIP_DB_BACKUP is set: migrating without a backup")
        return
    backup_dir = Path(settings.BACKUP_DIR)
    logger.info("Backup written to %s", create_backup(backup_dir))
    prune_backups(backup_dir, settings.BACKUP_KEEP)


def migrate() -> None:
    """
    Adopt a pre-Alembic database, back it up if needed, then upgrade.
    """
    config = build_alembic_config()
    state = asyncio.run(inspect_database())
    if needs_adoption(state.tables):
        command.stamp(config, BASELINE_REVISION)
        state = DatabaseState(state.tables, BASELINE_REVISION)
    head = ScriptDirectory.from_config(config).get_current_head()
    if needs_backup(state, head):
        back_up_before_migrating()
    command.upgrade(config, HEAD_REVISION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
