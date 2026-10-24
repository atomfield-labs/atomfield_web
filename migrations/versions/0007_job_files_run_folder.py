"""
jobs.output_files, runs.folder_path, runs.folder_address

Results stay on the machine that ran them. The server keeps a card per
file (path, size, sha256) and where the run's folder is, so the UI can
list files and show how to copy them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column(
        "jobs",
        sa.Column("output_files", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "runs", sa.Column("folder_path", sa.String(1024), nullable=True)
    )
    op.add_column(
        "runs", sa.Column("folder_address", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_column("runs", "folder_address")
    op.drop_column("runs", "folder_path")
    op.drop_column("jobs", "output_files")
