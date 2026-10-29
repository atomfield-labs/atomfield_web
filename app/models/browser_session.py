"""
SQLAlchemy ORM model for browser sessions: a person signed in on one
browser, which shows the secret in its cookie with every request.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class BrowserSession(Base):
    """
    One browser's sign-in, until it expires or the person signs out.
    The cookie's secret is stored only as a hash, like API keys.
    """

    __tablename__ = "browser_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs.

        :return: Whose session it is, and until when.
        :rtype: str
        """
        return f"<BrowserSession of {self.user_id} to {self.expires_at}>"
