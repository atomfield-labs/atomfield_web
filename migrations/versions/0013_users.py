"""
users

People own runs, compute targets and API keys, and carry the quota; a
key only identifies one person's scripts. Every existing key becomes a
person with the same id, so the owner columns already hold the right
ids and no row has to move. ``jobs.api_key_id`` becomes ``owner_id``.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-30 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, owner column) pairs, after this revision and before it.
OWNED = (
    ("jobs", "owner_id"),
    ("runs", "owner_id"),
    ("compute_targets", "owner_id"),
)
KEY_OWNED = (
    ("jobs", "api_key_id"),
    ("runs", "owner_id"),
    ("compute_targets", "owner_id"),
)
QUOTA_COLUMNS = ("quota_limit", "quota_used")


def user_columns() -> list[sa.Column]:
    """
    The users table's columns, made fresh for each use.

    :return: Columns.
    :rtype: list[sa.Column]
    """
    now = sa.text("now()")
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("quota_used", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    ]


def create_users() -> None:
    """
    The users table, filled with one person per existing key.
    """
    op.create_table(
        "users",
        *user_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.execute(
        "INSERT INTO users (id, name, is_admin, quota_limit, quota_used, "
        "is_active, created_at, last_seen_at) "
        "SELECT id, label, false, quota_limit, quota_used, is_active, "
        "created_at, last_used_at FROM api_keys"
    )


def give_keys_owners() -> None:
    """
    Each key belongs to the person made from it; the quota moves to
    the person.
    """
    op.add_column("api_keys", sa.Column("user_id", sa.UUID(), nullable=True))
    op.execute("UPDATE api_keys SET user_id = id")
    op.alter_column("api_keys", "user_id", nullable=False)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_foreign_key(
        "api_keys_user_id_fkey",
        "api_keys",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    for column in QUOTA_COLUMNS:
        op.drop_column("api_keys", column)


def point_owners_at(table_name: str, owned: tuple) -> None:
    """
    Make the owner columns reference ``table_name``.

    :param table_name: ``users`` going up, ``api_keys`` going down.
    :type table_name: str
    :param owned: (table, owner column) pairs.
    :type owned: tuple
    """
    for table, column in owned:
        op.create_foreign_key(
            f"{table}_{column}_fkey",
            table,
            table_name,
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def drop_owner_links(owned: tuple) -> None:
    """
    Remove the owner columns' foreign keys.

    :param owned: (table, owner column) pairs.
    :type owned: tuple
    """
    for table, column in owned:
        op.drop_constraint(f"{table}_{column}_fkey", table, type_="foreignkey")


def upgrade() -> None:
    """
    Apply this revision.
    """
    create_users()
    give_keys_owners()
    drop_owner_links(KEY_OWNED)
    op.alter_column("jobs", "api_key_id", new_column_name="owner_id")
    op.execute("ALTER INDEX ix_jobs_api_key_id RENAME TO ix_jobs_owner_id")
    point_owners_at("users", OWNED)


def quota_back_to_keys() -> None:
    """
    Going down, each key carries its person's quota again.
    """
    for column in QUOTA_COLUMNS:
        op.add_column("api_keys", sa.Column(column, sa.Integer()))
    op.execute(
        "UPDATE api_keys SET quota_limit = users.quota_limit, "
        "quota_used = users.quota_used FROM users "
        "WHERE users.id = api_keys.user_id"
    )
    for column in QUOTA_COLUMNS:
        op.alter_column("api_keys", column, nullable=False)


def owners_back_to_keys() -> None:
    """
    Going down, owners must be keys again: a person's rows go to their
    oldest key, or to nobody if they have none.
    """
    for table, column in OWNED:
        op.execute(
            f"UPDATE {table} SET {column} = (SELECT k.id FROM api_keys k "
            f"WHERE k.user_id = {table}.{column} "
            "ORDER BY k.created_at LIMIT 1) "
            f"WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN (SELECT id FROM api_keys)"
        )


def downgrade() -> None:
    """
    Revert this revision.
    """
    drop_owner_links(OWNED)
    quota_back_to_keys()
    owners_back_to_keys()
    op.execute("ALTER INDEX ix_jobs_owner_id RENAME TO ix_jobs_api_key_id")
    op.alter_column("jobs", "owner_id", new_column_name="api_key_id")
    point_owners_at("api_keys", KEY_OWNED)
    op.drop_constraint("api_keys_user_id_fkey", "api_keys", type_="foreignkey")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
    op.drop_table("users")
