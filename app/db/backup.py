"""
Database backups with ``pg_dump``, kept as a rolling set of files.

Used before migrations run, so a bad migration (or a mistaken command)
can always be undone with ``pg_restore``.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings

PG_DUMP = "pg_dump"
BACKUP_SUFFIX = ".dump"
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def build_backup_path(backup_dir: Path, moment: datetime) -> Path:
    """
    Name a backup after its database and UTC time, so names sort by age.

    :param backup_dir: Directory holding backups.
    :type backup_dir: Path
    :param moment: Time the backup is taken.
    :type moment: datetime
    :return: Path for the new dump file.
    :rtype: Path
    """
    stamp = moment.astimezone(UTC).strftime(TIMESTAMP_FORMAT)
    return backup_dir / f"{settings.POSTGRES_DB}-{stamp}{BACKUP_SUFFIX}"


def build_pg_dump_command(target: Path) -> list[str]:
    """
    Build the ``pg_dump`` argument list for the configured database.

    The password is not an argument: argument lists are visible to
    every user of the machine. It travels in ``PGPASSWORD`` instead.

    :param target: File to write the dump to.
    :type target: Path
    :return: Exec-form command.
    :rtype: list[str]
    """
    return [
        PG_DUMP,
        "--host", settings.POSTGRES_HOST,
        "--port", str(settings.POSTGRES_PORT),
        "--username", settings.POSTGRES_USER,
        "--dbname", settings.POSTGRES_DB,
        "--format", "custom",
        "--file", str(target),
    ]  # fmt: skip


def create_backup(backup_dir: Path) -> Path:
    """
    Dump the configured database to a new file in ``backup_dir``.

    :param backup_dir: Directory holding backups; created if missing.
    :type backup_dir: Path
    :return: Path of the dump that was written.
    :rtype: Path
    :raises RuntimeError: If ``pg_dump`` is not installed.
    :raises subprocess.CalledProcessError: If ``pg_dump`` fails.
    """
    if shutil.which(PG_DUMP) is None:
        raise RuntimeError(
            "pg_dump is not installed, so no backup can be taken. Install "
            "the PostgreSQL client, or set SKIP_DB_BACKUP=1 knowingly."
        )
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = build_backup_path(backup_dir, datetime.now(UTC))
    environment = {**os.environ, "PGPASSWORD": settings.POSTGRES_PASSWORD}
    subprocess.run(build_pg_dump_command(target), env=environment, check=True)
    return target


def prune_backups(backup_dir: Path, keep: int) -> list[Path]:
    """
    Delete all but the newest ``keep`` backups of this database.

    :param backup_dir: Directory holding backups.
    :type backup_dir: Path
    :param keep: Number of most recent backups to keep.
    :type keep: int
    :return: Paths that were deleted.
    :rtype: list[Path]
    """
    pattern = f"{settings.POSTGRES_DB}-*{BACKUP_SUFFIX}"
    newest_first = sorted(backup_dir.glob(pattern), reverse=True)
    expired = newest_first[keep:]
    for path in expired:
        path.unlink()
    return expired
