"""
run bundles

A run records when it finished and the state of its zip. Targets say
whether their runs are zipped and uploaded automatically: only the
house agent's, whose machine users cannot reach themselves.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-24 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HOUSE_TARGET_ID = "00000000-0000-0000-0000-000000000001"
FINAL = "('succeeded', 'failed', 'cancelled', 'upstream_failed')"
# Runs already over get a finish time; they are not zipped afterwards.
CLOSE_FINISHED_RUNS = f"""
UPDATE runs SET finished_at = now()
WHERE NOT EXISTS (
    SELECT 1 FROM jobs
    WHERE jobs.run_id = runs.id AND jobs.status NOT IN {FINAL}
)
"""


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.add_column(
        "compute_targets",
        sa.Column(
            "bundles_automatically",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        "UPDATE compute_targets SET bundles_automatically = true "
        f"WHERE id = '{HOUSE_TARGET_ID}'"
    )
    timestamp = sa.DateTime(timezone=True)
    op.add_column("runs", sa.Column("finished_at", timestamp, nullable=True))
    op.add_column(
        "runs",
        sa.Column(
            "bundle_status",
            sa.String(20),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column("runs", sa.Column("bundle_size", sa.BigInteger()))
    op.add_column("runs", sa.Column("bundle_requested_at", timestamp))
    op.add_column("runs", sa.Column("bundle_expires_at", timestamp))
    op.add_column("runs", sa.Column("bundle_error", sa.Text()))
    op.execute(CLOSE_FINISHED_RUNS)


def downgrade() -> None:
    """
    Revert this revision.
    """
    for column in (
        "bundle_error",
        "bundle_expires_at",
        "bundle_requested_at",
        "bundle_size",
        "bundle_status",
        "finished_at",
    ):
        op.drop_column("runs", column)
    op.drop_column("compute_targets", "bundles_automatically")
