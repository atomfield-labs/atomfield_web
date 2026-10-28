"""
data_packs

A data pack is a zip of files tasks read (pseudopotentials, model
weights), published once and downloaded once per machine. Tasks name
the packs they need in the catalog; a release can only be published
once every pack it names exists.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply this revision.
    """
    op.create_table(
        "data_packs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "version", name="uq_data_packs_name_version"
        ),
    )


def downgrade() -> None:
    """
    Revert this revision.
    """
    op.drop_table("data_packs")
