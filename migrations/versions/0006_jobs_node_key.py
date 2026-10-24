"""
jobs.node_key

Each job gets a folder name unique within its run (the node's name in
the pipeline), so a run's files read as runs/<run>/opt/, runs/<run>/md/
instead of job UUIDs. Existing jobs are named job_<id>.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNIQUE_NAME = "jobs_run_id_node_key_key"


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column("jobs", sa.Column("node_key", sa.String(80), nullable=True))
    op.execute("UPDATE jobs SET node_key = 'job_' || id::text")
    op.alter_column("jobs", "node_key", nullable=False)
    op.create_unique_constraint(UNIQUE_NAME, "jobs", ["run_id", "node_key"])


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_constraint(UNIQUE_NAME, "jobs", type_="unique")
    op.drop_column("jobs", "node_key")
