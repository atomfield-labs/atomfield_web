"""
SQLAlchemy ORM model for user API keys and execution quotas.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ApiKey(Base):
    """
    User credential representation for API authentication and quota tracking.
    """

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(20), nullable=False)
    label = Column(String(100), nullable=True)
    quota_limit = Column(Integer, default=100, nullable=False)
    quota_used = Column(Integer, default=0, nullable=False)
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
