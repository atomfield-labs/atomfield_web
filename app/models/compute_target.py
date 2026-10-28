"""
SQLAlchemy ORM model for compute targets: the machines agents run on.
"""

import uuid

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

# The platform's own agent. Fixed so migrations and startup code can
# refer to it without a lookup.
HOUSE_TARGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ComputeTarget(Base):
    """
    A machine that runs jobs through an agent: the platform's own
    server, a user's laptop, or a cluster login node.
    """

    __tablename__ = "compute_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # None for shared targets such as the house agent.
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False, default="process")
    # SHA-256 of the agent's token; None until a token is issued.
    token_hash = Column(String(64), nullable=True, unique=True)
    max_jobs = Column(Integer, nullable=False, default=4)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    # Zip and upload each finished run. Only for machines users cannot
    # reach themselves (ours); elsewhere results stay where they ran.
    bundles_automatically = Column(Boolean, nullable=False, default=False)
    # Deleted by its owner: no longer listed and its token no longer
    # works, but past runs keep pointing at it.
    retired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
