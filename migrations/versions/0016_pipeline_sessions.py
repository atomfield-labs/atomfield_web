"""
pipeline sessions

A person's pipelines move from the browser to the server, so they follow
the person to any computer and nobody else on that browser sees them.
Pipeline runs that already exist are listed, untitled and with no draft:
drafts lived in browsers, out of reach here. A single job's session
(``job_<id>``) was never listed, and is not now.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-31 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWEST_RUN_OF_EACH_SESSION = """
INSERT INTO pipeline_sessions
    (owner_id, id, node_count, run_id, job_ids, created_at, updated_at)
SELECT DISTINCT ON (runs.owner_id, runs.session_id)
    runs.owner_id,
    runs.session_id,
    (SELECT count(*) FROM jobs WHERE jobs.run_id = runs.id),
    runs.id,
    '{}'::jsonb,
    runs.created_at,
    runs.created_at
FROM runs
WHERE runs.owner_id IS NOT NULL AND runs.session_id NOT LIKE 'job\\_%'
ORDER BY runs.owner_id, runs.session_id, runs.created_at DESC
"""


def session_columns() -> list[sa.Column]:
    """
    The pipeline_sessions table's columns.

    :return: Columns.
    :rtype: list[sa.Column]
    """
    now = sa.text("now()")
    return [
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("blueprint", postgresql.JSONB(), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("job_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now),
    ]


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "pipeline_sessions",
        *session_columns(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("owner_id", "id"),
    )
    op.execute(NEWEST_RUN_OF_EACH_SESSION)


def downgrade() -> None:
    """
    Revert this revision: names and drafts kept here are lost.
    """
    op.drop_table("pipeline_sessions")
