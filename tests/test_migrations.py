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


async def run_sql(*statements: str) -> list[list[tuple]]:
    """
    Run SQL statements in one transaction on the configured database.

    :param statements: SQL to execute, in order.
    :type statements: str
    :return: Rows returned by each statement (empty if none).
    :rtype: list[list[tuple]]
    """
    engine = create_async_engine(settings.database_url)
    results = []
    try:
        async with engine.begin() as connection:
            for statement in statements:
                result = await connection.execute(text(statement))
                rows = result.all() if result.returns_rows else []
                results.append([tuple(row) for row in rows])
    finally:
        await engine.dispose()
    return results


async def drop_version_table() -> None:
    """
    Forget the migration history, as a pre-Alembic database would.
    """
    await run_sql(f"DROP TABLE {VERSION_TABLE}")


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


KEY = "11111111-1111-1111-1111-111111111111"
OTHER_KEY = "22222222-2222-2222-2222-222222222222"
TARGET = "33333333-3333-3333-3333-333333333333"
OLDER_RUN = "44444444-4444-4444-4444-444444444444"
NEWER_RUN = "55555555-5555-5555-5555-555555555555"
JOB_RUN = "66666666-6666-6666-6666-666666666666"
RUN_COLUMNS = (
    "(id, owner_id, session_id, target_id, event_seq, bundle_status, "
    "created_at)"
)
PAST_RUNS = [
    (
        "INSERT INTO users (id, role, quota_limit, quota_used, is_active) "
        f"VALUES ('{KEY}', 'user', 1, 0, true)"
    ),
    (
        "INSERT INTO compute_targets (id, name, kind, max_jobs, "
        "bundles_automatically) "
        f"VALUES ('{TARGET}', 't', 'local', 1, false)"
    ),
    (
        f"INSERT INTO runs {RUN_COLUMNS} VALUES ('{OLDER_RUN}', '{KEY}', "
        f"'pipeline_a', '{TARGET}', 0, 'none', now() - interval '1 hour')"
    ),
    (
        f"INSERT INTO runs {RUN_COLUMNS} VALUES ('{NEWER_RUN}', '{KEY}', "
        f"'pipeline_a', '{TARGET}', 0, 'none', now())"
    ),
    (
        f"INSERT INTO runs {RUN_COLUMNS} VALUES ('{JOB_RUN}', '{KEY}', "
        f"'job_b', '{TARGET}', 0, 'none', now())"
    ),
    (
        "INSERT INTO jobs (id, script_name, node_key, status, run_id, "
        "pending_parents, attempt, max_attempts) VALUES "
        "('77777777-7777-7777-7777-777777777777', 'x', 'x', 'queued', "
        f"'{NEWER_RUN}', 0, 0, 2)"
    ),
]
JOB_A, JOB_B, JOB_C, JOB_D, JOB_E = (
    f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 6)
)
PIPELINE_P1 = '{"pipeline_id": "p1"}'
LEGACY_ROWS = [
    (
        "INSERT INTO api_keys (id, key_hash, key_prefix, quota_limit, "
        f"quota_used, is_active) VALUES ('{KEY}', 'h', 'p', 10, 0, true)"
    ),
    # Pipeline p1: A and C feed B; A succeeded, C was mid-run; D was
    # marked failed by the old cascade. E is a standalone job.
    (
        "INSERT INTO jobs (id, script_name, status, parameters, "
        "api_key_id, error_message) VALUES "
        f"('{JOB_A}', 'xtb_opt', 'Success', '{PIPELINE_P1}', '{KEY}', NULL),"
        f"('{JOB_B}', 'xtb_md', 'Blocked', '{PIPELINE_P1}', '{KEY}', NULL),"
        f"('{JOB_C}', 'xtb_opt', 'Running', '{PIPELINE_P1}', '{KEY}', NULL),"
        f"('{JOB_D}', 'xtb_md', 'Failed', '{PIPELINE_P1}', '{KEY}', "
        "'Upstream dependency failed'),"
        f"('{JOB_E}', 'xtb_opt', 'Pending', '{{}}', '{KEY}', NULL)"
    ),
    (
        "INSERT INTO job_dependencies (upstream_id, downstream_id) VALUES "
        f"('{JOB_A}', '{JOB_B}'), ('{JOB_C}', '{JOB_B}')"
    ),
]


def test_0004_converts_existing_jobs(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Old statuses map to the new states, every job gets a run (one per
    pipeline), waiting jobs count their unfinished parents, and a
    downgrade restores the old strings.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for the reverse check.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = build_alembic_config()
    command.upgrade(config, "0003")
    asyncio.run(run_sql(*LEGACY_ROWS))

    command.upgrade(config, "0004")

    jobs, runs = asyncio.run(
        run_sql(
            "SELECT id::text, status, pending_parents, run_id::text "
            "FROM jobs ORDER BY id",
            "SELECT session_id FROM runs ORDER BY session_id",
        )
    )
    statuses = {job_id: status for job_id, status, _, _ in jobs}
    assert statuses == {
        JOB_A: "succeeded",
        JOB_B: "waiting",
        JOB_C: "queued",
        JOB_D: "upstream_failed",
        JOB_E: "queued",
    }
    pending = {job_id: count for job_id, _, count, _ in jobs}
    assert pending[JOB_B] == 1
    run_of = {job_id: run_id for job_id, _, _, run_id in jobs}
    assert len({run_of[j] for j in (JOB_A, JOB_B, JOB_C, JOB_D)}) == 1
    assert runs == [(f"job_{JOB_E}",), ("p1",)]

    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    command.downgrade(config, "0003")
    (restored,) = asyncio.run(run_sql("SELECT status FROM jobs ORDER BY id"))
    assert restored == [
        ("Success",),
        ("Blocked",),
        ("Pending",),
        ("Failed",),
        ("Pending",),
    ]


def test_0013_makes_each_key_a_person(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Every key becomes a person with the same id who carries its quota,
    so jobs and runs keep their owners; a downgrade puts the quota back
    on the key.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for the reverse check.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = build_alembic_config()
    command.upgrade(config, "0003")
    asyncio.run(run_sql(*LEGACY_ROWS))

    command.upgrade(config, "0013")

    users, owners = asyncio.run(
        run_sql(
            "SELECT id::text, quota_limit, is_admin FROM users",
            "SELECT DISTINCT owner_id::text FROM jobs",
        )
    )
    assert users == [(KEY, 10, False)]
    assert owners == [(KEY,)]

    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    command.downgrade(config, "0012")
    (keys,) = asyncio.run(run_sql("SELECT id::text, quota_limit FROM api_keys"))
    assert keys == [(KEY, 10)]


def test_0015_turns_the_administrator_into_the_owner(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Whoever was the administrator becomes the owner, everyone else a
    user with no lab; going back, only owners are administrators.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for the reverse check.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = build_alembic_config()
    command.upgrade(config, "0014")
    columns = "(id, name, is_admin, quota_limit, quota_used, is_active)"
    asyncio.run(
        run_sql(
            f"INSERT INTO users {columns} VALUES "
            f"('{KEY}', 'them', true, 1, 0, true), "
            f"('{OTHER_KEY}', 'me', false, 1, 0, true)"
        )
    )

    command.upgrade(config, "0015")

    (people,) = asyncio.run(
        run_sql("SELECT name, role, lab_id FROM users ORDER BY name")
    )
    assert people == [("me", "user", None), ("them", "owner", None)]

    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    command.downgrade(config, "0014")
    (admins,) = asyncio.run(
        run_sql("SELECT name, is_admin FROM users ORDER BY name")
    )
    assert admins == [("me", False), ("them", True)]


def test_0016_lists_past_pipeline_runs(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Each person's pipeline sessions are listed from their newest run,
    with its job count; a single job's session is not listed.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for the reverse check.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = build_alembic_config()
    command.upgrade(config, "0015")
    asyncio.run(run_sql(*PAST_RUNS))

    command.upgrade(config, "0016")

    (sessions,) = asyncio.run(
        run_sql(
            "SELECT id, title, node_count, run_id::text, job_ids::text "
            "FROM pipeline_sessions"
        )
    )
    assert sessions == [("pipeline_a", None, 1, NEWER_RUN, "{}")]

    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    command.downgrade(config, "0015")


def test_0017_gives_old_releases_a_wheel_for_everything(
    scratch_database: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A release from before compiled packages keeps its one wheel, for any
    package on any machine.

    :param scratch_database: Name of the scratch database.
    :type scratch_database: str
    :param monkeypatch: Sets ALLOW_DOWNGRADE for the reverse check.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = build_alembic_config()
    command.upgrade(config, "0016")
    asyncio.run(
        run_sql(
            "INSERT INTO script_releases (id, name, version, sha256, catalog) "
            f"VALUES ('{KEY}', 'toy', '1', 'abc', '{{}}')"
        )
    )

    command.upgrade(config, "0017")

    (wheels,) = asyncio.run(
        run_sql("SELECT package, machine, sha256 FROM release_wheels")
    )
    assert wheels == [("any", "any", "abc")]

    monkeypatch.setenv("ALLOW_DOWNGRADE", "1")
    command.downgrade(config, "0016")
