"""
SQLAlchemy ORM model for runs: one submitted pipeline (or single job).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Run(Base):
    """
    One submission. All of a run's jobs execute on the same compute
    target, so their files never have to move between machines.
    """

    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The UI session (pipeline_id) the run was submitted from.
    session_id = Column(String(64), nullable=False, index=True)
    target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("compute_targets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
