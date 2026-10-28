"""
jobs.scheduled, compute_targets.retired_at

A job handed to a cluster scheduler keeps running while its agent is
silent, so the server waits much longer (24 h) before calling it lost
than for a job that dies with its agent (3 min). Targets can be
retired: hidden and locked out, while their runs keep their history.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-27 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column(
        "jobs",
        sa.Column(
            "scheduled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "compute_targets",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_column("compute_targets", "retired_at")
    op.drop_column("jobs", "scheduled")
