"""
release wheels

A release is now one wheel per package (workflow) and kind of machine,
compiled, so each job gets only its own package's file. Releases already
published keep their one plain wheel, for any package on any machine.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-01 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXISTING_WHEELS = """
INSERT INTO release_wheels (release_id, package, machine, sha256)
SELECT id, 'any', 'any', sha256 FROM script_releases
"""


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "release_wheels",
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("package", sa.String(length=64), nullable=False),
        sa.Column("machine", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["script_releases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("release_id", "package", "machine"),
    )
    op.execute(EXISTING_WHEELS)


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_table("release_wheels")
