"""
runs, compute targets, job leases

Adds the tables and columns the job engine needs, and converts existing
rows: old status strings map to the new states, every job gets a run,
and waiting jobs get their count of unfinished parents.

Values are written out here instead of imported from app code: a
migration is a snapshot and must not change when the app does.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HOUSE_TARGET_ID = "00000000-0000-0000-0000-000000000001"
RUN_FK = "jobs_run_id_fkey"
AGENT_FK = "jobs_agent_id_fkey"

STATUS_UP = """
UPDATE jobs SET status = CASE
    WHEN status = 'Failed'
         AND error_message = 'Upstream dependency failed'
        THEN 'upstream_failed'
    WHEN status IN ('Pending', 'Ready', 'Running') THEN 'queued'
    WHEN status = 'Blocked' THEN 'waiting'
    WHEN status = 'Success' THEN 'succeeded'
    WHEN status = 'Failed' THEN 'failed'
    ELSE status
END
"""

STATUS_DOWN = """
UPDATE jobs SET status = CASE
    WHEN status = 'queued' THEN 'Pending'
    WHEN status = 'waiting' THEN 'Blocked'
    WHEN status = 'running' THEN 'Running'
    WHEN status = 'succeeded' THEN 'Success'
    WHEN status IN ('failed', 'upstream_failed', 'cancelled') THEN 'Failed'
    ELSE status
END
"""

# One run per (owner, pipeline); a job without a pipeline is its own run.
JOB_SESSION = (
    "coalesce(jobs.parameters->>'pipeline_id', 'job_' || jobs.id::text)"
)

CREATE_RUNS = f"""
INSERT INTO runs (id, owner_id, session_id, target_id, created_at)
SELECT gen_random_uuid(), api_key_id, session_id,
       '{HOUSE_TARGET_ID}', min(created_at)
FROM (SELECT api_key_id, {JOB_SESSION} AS session_id, created_at
      FROM jobs) AS job_sessions
GROUP BY api_key_id, session_id
"""

LINK_RUNS = f"""
UPDATE jobs SET run_id = runs.id
FROM runs
WHERE runs.session_id = {JOB_SESSION}
  AND runs.owner_id IS NOT DISTINCT FROM jobs.api_key_id
"""

COUNT_PENDING_PARENTS = """
UPDATE jobs AS child SET pending_parents = (
    SELECT count(*)
    FROM job_dependencies AS edge
    JOIN jobs AS parent ON parent.id = edge.upstream_id
    WHERE edge.downstream_id = child.id AND parent.status <> 'succeeded'
)
WHERE child.status = 'waiting'
"""


def create_compute_targets() -> None:
    """
    Create the compute target table and the house agent's row.
    """
    op.create_table(
        "compute_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("max_jobs", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["api_keys.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_compute_targets_owner_id"), "compute_targets", ["owner_id"]
    )
    op.execute(
        "INSERT INTO compute_targets (id, name, kind, max_jobs) "
        f"VALUES ('{HOUSE_TARGET_ID}', 'house', 'process', 4)"
    )


def create_runs() -> None:
    """
    Create the run table.
    """
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["api_keys.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["compute_targets.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_owner_id"), "runs", ["owner_id"])
    op.create_index(op.f("ix_runs_session_id"), "runs", ["session_id"])


def add_job_columns() -> None:
    """
    Add lease and dependency columns to jobs. Server defaults let the
    NOT NULL columns be added to a table that already has rows.
    """
    zero = sa.text("0")
    timestamp = sa.DateTime(timezone=True)
    columns = [
        # Filled in by the data steps, then made NOT NULL in upgrade().
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column(
            "pending_parents", sa.Integer(), nullable=False, server_default=zero
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=zero),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("last_heartbeat_at", timestamp, nullable=True),
        sa.Column("deadline_at", timestamp, nullable=True),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    ]
    for column in columns:
        op.add_column("jobs", column)
    op.create_index(op.f("ix_jobs_agent_id"), "jobs", ["agent_id"])
    op.create_index(op.f("ix_jobs_run_id"), "jobs", ["run_id"])
    op.create_foreign_key(
        AGENT_FK,
        "jobs",
        "compute_targets",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        RUN_FK, "jobs", "runs", ["run_id"], ["id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    """
    Apply this revision: schema first, then convert existing rows.
    """
    create_compute_targets()
    create_runs()
    add_job_columns()
    op.execute(STATUS_UP)
    op.execute(CREATE_RUNS)
    op.execute(LINK_RUNS)
    op.execute(COUNT_PENDING_PARENTS)
    op.alter_column("jobs", "run_id", nullable=False)


def downgrade() -> None:
    """
    Revert this revision; statuses map back to the old strings.
    """
    op.execute(STATUS_DOWN)
    op.drop_constraint(RUN_FK, "jobs", type_="foreignkey")
    op.drop_constraint(AGENT_FK, "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_run_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_agent_id"), table_name="jobs")
    for name in (
        "cancel_requested",
        "deadline_at",
        "last_heartbeat_at",
        "agent_id",
        "max_attempts",
        "attempt",
        "pending_parents",
        "run_id",
    ):
        op.drop_column("jobs", name)
    op.drop_index(op.f("ix_runs_session_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_owner_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_index(op.f("ix_compute_targets_owner_id"), "compute_targets")
    op.drop_table("compute_targets")
