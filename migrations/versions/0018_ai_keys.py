"""
ai keys

Each person's own key for an AI vendor, encrypted, for AI help on a
finished step.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-02 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "ai_keys",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("vendor", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("sealed_key", sa.Text(), nullable=False),
        sa.Column("key_ending", sa.String(length=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_table("ai_keys")
