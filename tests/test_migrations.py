"""
Guards for the migration history, adoption, backups and downgrades.

Most tests run on a scratch database so they can build, adopt and drop
schemas without touching the session's shared test database.
"""

import asyncio
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.db.migrate import (
    BASELINE_REVISION,
    BASELINE_TABLES,
    VERSION_TABLE,
    DatabaseState,
    build_alembic_config,
    inspect_database,
    migrate,
    needs_adoption,
    needs_backup,
)
from tests.stores import drop_test_database, recreate_test_database

SCRATCH_DATABASE = "atomfield_migrations_test"
# Read from migrations/, so adding a revision never breaks these tests.
HEAD = ScriptDirectory.from_config(build_alembic_config()).get_current_head()


@pytest.fixture
def scratch_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """
    Point the settings at an empty scratch database for one test.

    :param monkeypatch: Restores the original settings afterwards.
    :type monkeypatch: pytest.MonkeyPatch
    :return: Name of the scratch database.
    :rtype: Iterator[str]
    """
    monkeypatch.setattr(settings, "POSTGRES_DB", SCRATCH_DATABASE)
    monkeypatch.delenv("ALLOW_DOWNGRADE", raising=False)
    asyncio.run(recreate_test_database())
    yield SCRATCH_DATABASE
    asyncio.run(drop_test_database())


async def drop_version_table() -> None:
    """
    Forget the migration history, as a pre-Alembic database would.
    """
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE {VERSION_TABLE}"))
    finally:
        await engine.dispose()


def test_migrations_match_models(client: TestClient):
    """
    The migrated schema equals what the ORM models describe.

    Fails when someone changes a model but forgets the migration,
    the mistake that otherwise surfaces only in production.

    :param client: In-process API client; its fixture migrated the DB.
    :type client: TestClient
    """
    command.check(build_alembic_config())


def test_migrate_builds_an_empty_database(scratch_database: str):
    """
    An empty database is migrated straight to head, without a backup.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    """
    migrate()

    state = asyncio.run(inspect_database())
    assert state.revision == HEAD
    assert BASELINE_TABLES <= state.tables
    command.check(build_alembic_config())


def test_migrate_adopts_a_pre_alembic_database(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Old tables without history are stamped, then upgraded to head.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Skips the backup, which needs pg_dump.
    :type monkeypatch: pytest.MonkeyPatch
    """
    command.upgrade(build_alembic_config(), BASELINE_REVISION)
    asyncio.run(drop_version_table())
    monkeypatch.setattr(settings, "SKIP_DB_BACKUP", True)

    migrate()

    assert asyncio.run(inspect_database()).revision == HEAD
    command.check(build_alembic_config())


def test_downgrade_is_refused_without_permission(scratch_database: str):
    """
    A downgrade without ALLOW_DOWNGRADE=1 fails and changes nothing.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    """
    migrate()

    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(build_alembic_config(), "base")

    state = asyncio.run(inspect_database())
    assert state.revision == HEAD
    assert BASELINE_TABLES <= state.tables


def test_downgrade_round_trip_with_permission(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    With the opt-in, every migration can be undone and re-applied.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for this test only.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    config = build_alembic_config()
    migrate()

    command.downgrade(config, "base")
    assert asyncio.run(inspect_database()).tables == {VERSION_TABLE}

    command.upgrade(config, "head")
    command.check(config)


def test_adoption_only_for_pre_alembic_databases():
    """
    Only a database with baseline tables and no history is adopted.
    """
    assert needs_adoption(BASELINE_TABLES)
    assert not needs_adoption(BASELINE_TABLES | {VERSION_TABLE})
    assert not needs_adoption(frozenset())
    assert not needs_adoption(frozenset({VERSION_TABLE}))


def test_backup_only_when_existing_data_would_change():
    """
    Back up a database with tables and pending migrations, nothing else.
    """
    with_data = BASELINE_TABLES | {VERSION_TABLE}
    assert needs_backup(DatabaseState(with_data, BASELINE_REVISION), HEAD)
    assert not needs_backup(DatabaseState(with_data, HEAD), HEAD)
    assert not needs_backup(DatabaseState(frozenset(), None), HEAD)
    empty_but_stamped = frozenset({VERSION_TABLE})
    assert not needs_backup(DatabaseState(empty_but_stamped, None), HEAD)
