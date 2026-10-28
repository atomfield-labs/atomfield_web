"""
jobs.started_at

A job handed to a cluster scheduler can wait in its queue for hours
after the agent claims it. Its clock (and deadline) starts when it
really begins running, which the agent reports. Jobs running now were
started by agents that run them at once.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-24 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column(
        "jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE jobs SET started_at = last_heartbeat_at "
        "WHERE status = 'running'"
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_column("jobs", "started_at")
