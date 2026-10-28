"""
script_releases, runs.release_id

A release is a published version of the scripts: a wheel with its
catalog inside. A run is pinned to the release that was current when
it was submitted, so all its jobs and retries run the same code.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RELEASE_FK = "fk_runs_release_id_script_releases"


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "script_releases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("git_commit", sa.String(length=40), nullable=True),
        sa.Column(
            "catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "version", name="uq_script_releases_name_version"
        ),
    )
    op.create_index(
        op.f("ix_script_releases_published_at"),
        "script_releases",
        ["published_at"],
    )
    op.add_column("runs", sa.Column("release_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        RELEASE_FK,
        "runs",
        "script_releases",
        ["release_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_constraint(RELEASE_FK, "runs", type_="foreignkey")
    op.drop_column("runs", "release_id")
    op.drop_index(
        op.f("ix_script_releases_published_at"), table_name="script_releases"
    )
    op.drop_table("script_releases")
