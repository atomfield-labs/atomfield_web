"""
runs.event_seq

Each run counts the job changes it has announced. Every event carries
the counter's value, so a watcher can tell an old event from a new one
and notice one it missed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column(
        "runs",
        sa.Column(
            "event_seq",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_column("runs", "event_seq")
