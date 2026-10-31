"""
roles and labs

A person now has a role: the platform's owner (who was the
administrator), a lab's admin, or a user. A lab holds the workflows the
owner gives it, and a person the ones their lab's admin gives them.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-31 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LAB_LINK = "users_lab_id_fkey"


def create_labs() -> None:
    """
    The labs.
    """
    now = sa.text("now()")
    op.create_table(
        "labs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def create_ticks(table: str, column: str, target: str) -> None:
    """
    A table of who was given which workflow.

    :param table: The table's name.
    :type table: str
    :param column: The column naming who was given it.
    :type column: str
    :param target: What that column references.
    :type target: str
    """
    op.create_table(
        table,
        sa.Column(column, sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint([column], [target], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(column, "workflow_id"),
    )


def upgrade() -> None:
    """
    Apply this revision.
    """
    create_labs()
    create_ticks("lab_workflows", "lab_id", "labs.id")
    create_ticks("user_workflows", "user_id", "users.id")
    op.add_column("users", sa.Column("role", sa.String(length=20)))
    op.execute(
        "UPDATE users SET role = "
        "CASE WHEN is_admin THEN 'owner' ELSE 'user' END"
    )
    op.alter_column("users", "role", nullable=False)
    op.drop_column("users", "is_admin")
    op.add_column("users", sa.Column("lab_id", sa.UUID(), nullable=True))
    op.create_index("ix_users_lab_id", "users", ["lab_id"])
    op.create_foreign_key(
        LAB_LINK, "users", "labs", ["lab_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """
    Revert this revision: labs are forgotten, and only owners stay
    administrators.
    """
    op.drop_constraint(LAB_LINK, "users", type_="foreignkey")
    op.drop_index("ix_users_lab_id", table_name="users")
    op.drop_column("users", "lab_id")
    op.add_column("users", sa.Column("is_admin", sa.Boolean()))
    op.execute("UPDATE users SET is_admin = (role = 'owner')")
    op.alter_column("users", "is_admin", nullable=False)
    op.drop_column("users", "role")
    op.drop_table("user_workflows")
    op.drop_table("lab_workflows")
    op.drop_table("labs")
