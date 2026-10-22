"""
index job_dependencies.downstream_id

The model declared this index after some databases were created, and
create_all never alters existing tables, so older databases lack it.
IF NOT EXISTS makes the upgrade correct for both kinds of database.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22 22:50:18.856420
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_job_dependencies_downstream_id"
TABLE_NAME = "job_dependencies"


def upgrade() -> None:
    """
    Create the downstream lookup index unless it already exists.
    """
    op.create_index(
        op.f(INDEX_NAME),
        TABLE_NAME,
        ["downstream_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """
    Drop the downstream lookup index.
    """
    op.drop_index(op.f(INDEX_NAME), table_name=TABLE_NAME, if_exists=True)
