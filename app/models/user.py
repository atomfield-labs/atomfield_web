"""
SQLAlchemy ORM model for people: who owns runs, compute targets and
API keys, and how many jobs they may run.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

# Jobs a new person may submit, until the owner changes it.
DEFAULT_QUOTA_LIMIT = 100
NAME_LENGTH = 100


class Role(StrEnum):
    """
    What a person may do. The owner runs the platform and gives labs
    their workflows; a lab's admin gives its people theirs; a user
    runs what they are given.
    """

    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """
    A person. Owns runs, compute targets and API keys, and a quota.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Set by signing in; empty for people from before sign-in existed.
    email = Column(String(320), nullable=True, unique=True)
    name = Column(String(NAME_LENGTH), nullable=True)
    role = Column(String(20), nullable=False, default=Role.USER)
    # Whose lab they are in; none for an owner, or someone removed.
    lab_id = Column(
        UUID(as_uuid=True),
        ForeignKey("labs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quota_limit = Column(Integer, nullable=False, default=DEFAULT_QUOTA_LIMIT)
    quota_used = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_owner(self) -> bool:
        """
        Whether this person owns the platform.

        :return: True for an owner.
        :rtype: bool
        """
        return self.role == Role.OWNER

    @property
    def quota_remaining(self) -> int:
        """
        Jobs this person may still submit.

        :return: What is left of their quota, never below zero.
        :rtype: int
        """
        return max(0, self.quota_limit - self.quota_used)

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs.

        :return: The person's email or name.
        :rtype: str
        """
        return f"<User {self.email or self.name or self.id}>"
