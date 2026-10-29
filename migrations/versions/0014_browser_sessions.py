"""
browser sessions

People sign in on a browser with their institute account; the browser
then shows a secret in its cookie, stored here only as a hash, until
the session expires or they sign out.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-30 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def session_columns() -> list[sa.Column]:
    """
    The browser_sessions table's columns.

    :return: Columns.
    :rtype: list[sa.Column]
    """
    now = sa.text("now()")
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "browser_sessions",
        *session_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_browser_sessions_token_hash"),
        "browser_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_browser_sessions_user_id"), "browser_sessions", ["user_id"]
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_table("browser_sessions")
