"""
SQLAlchemy ORM model for API keys: what a person's scripts use to call
the API.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ApiKey(Base):
    """
    A key one person's scripts use; a person may have several.
    """

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(20), nullable=False)
    label = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """
        Produce concise string representation for debugging and logging.

        :return: Human-readable API key summary string.
        :rtype: str
        """
        label_str = self.label or "Anonymous"
        return f"<ApiKey {self.key_prefix} ({label_str})>"
