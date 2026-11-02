"""
SQLAlchemy ORM models for AI help: each person's key for a vendor, and
what a model said about a step.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base

VENDOR_NAME_LENGTH = 20
MODEL_NAME_LENGTH = 100
KEY_ENDING_LENGTH = 4
REVIEW_FIELD_LENGTH = 20


class ReviewStatus(StrEnum):
    """
    Where a review is: running, then done or failed.
    """

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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


class AiReview(Base):
    """
    One click of an AI button: what a model read about a step, and what it
    said. Only one can run per job, so a double click can't pay twice.
    """

    __tablename__ = "ai_reviews"
    __table_args__ = (
        Index(
            "ai_reviews_one_running",
            "job_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Whose key pays, which may not be the job's owner's.
    requested_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind = Column(String(REVIEW_FIELD_LENGTH), nullable=False)
    status = Column(
        String(REVIEW_FIELD_LENGTH),
        nullable=False,
        default=ReviewStatus.RUNNING,
    )
    vendor = Column(String(VENDOR_NAME_LENGTH), nullable=False)
    model = Column(String(MODEL_NAME_LENGTH), nullable=False)
    # A fallback can answer in place of the model asked.
    answered_by = Column(String(MODEL_NAME_LENGTH), nullable=True)
    summary = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    suggestions = Column(JSONB, nullable=True)
    check_next = Column(JSONB, nullable=True)
    # What the model was given: each file or page, and how much of it.
    read_parts = Column(JSONB, nullable=True)
    unread_pages = Column(JSONB, nullable=True)
    left_behind = Column(JSONB, nullable=True)
    # Written for the person; never the vendor's own text.
    error = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs.

        :return: The kind and the status.
        :rtype: str
        """
        return f"<AiReview {self.kind} {self.status}>"
