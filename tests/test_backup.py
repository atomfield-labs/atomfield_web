"""
Tests for pg_dump backups and their rolling retention.
"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.backup import (
    build_backup_path,
    build_pg_dump_command,
    create_backup,
    prune_backups,
)

START = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def test_backup_names_sort_oldest_first(tmp_path: Path):
    """
    Timestamped names sort in time order, which pruning relies on.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    moments = [START + timedelta(hours=hours) for hours in (0, 1, 13)]
    names = [build_backup_path(tmp_path, moment).name for moment in moments]
    assert names == sorted(names)
    assert names[0].startswith(f"{settings.POSTGRES_DB}-")


def test_prune_keeps_the_newest_backups(tmp_path: Path):
    """
    Only the newest backups survive; other databases' files are kept.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    backups = [
        build_backup_path(tmp_path, START + timedelta(days=day))
        for day in range(5)
    ]
    for path in backups:
        path.touch()
    unrelated = tmp_path / "other_db-20200101T000000Z.dump"
    unrelated.touch()

    deleted = prune_backups(tmp_path, keep=2)

    assert sorted(deleted) == backups[:3]
    assert sorted(tmp_path.iterdir()) == sorted([*backups[3:], unrelated])


def test_pg_dump_command_never_contains_the_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    The password stays out of the argument list, which other users see.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    :param monkeypatch: Sets a password that cannot match other args.
    :type monkeypatch: pytest.MonkeyPatch
    """
    password = "distinct-test-password"
    monkeypatch.setattr(settings, "POSTGRES_PASSWORD", password)
    command = build_pg_dump_command(tmp_path / "out.dump")
    assert not any(password in argument for argument in command)
    assert command[0] == "pg_dump"


@pytest.mark.skipif(
    shutil.which("pg_dump") is None,
    reason="pg_dump is not installed",
)
def test_create_backup_writes_a_dump(client: TestClient, tmp_path: Path):
    """
    A real dump of the test database is written and is not empty.

    :param client: In-process API client; its fixture migrated the DB.
    :type client: TestClient
    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    dump = create_backup(tmp_path)
    assert dump.exists()
    assert dump.stat().st_size > 0
