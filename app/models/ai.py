"""
SQLAlchemy ORM models for AI help: each person's key for a vendor.
"""

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

VENDOR_NAME_LENGTH = 20
MODEL_NAME_LENGTH = 100
KEY_ENDING_LENGTH = 4


class AiKey(Base):
    """
    A person's key for an AI vendor, encrypted (``KeyVault``). One each:
    saving another replaces it.
    """

    __tablename__ = "ai_keys"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    vendor = Column(String(VENDOR_NAME_LENGTH), nullable=False)
    model = Column(String(MODEL_NAME_LENGTH), nullable=False)
    sealed_key = Column(Text, nullable=False)
    # Shown to tell keys apart: never enough to use.
    key_ending = Column(String(KEY_ENDING_LENGTH), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs, without the
        key.

        :return: The vendor and the model.
        :rtype: str
        """
        return f"<AiKey {self.vendor} {self.model}>"
