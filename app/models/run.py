"""
SQLAlchemy ORM model for runs: one submitted pipeline (or single job).
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
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
        ForeignKey("users.id", ondelete="SET NULL"),
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
    # The scripts release every job of the run uses, retries included;
    # none for runs from before the first release.
    release_id = Column(
        UUID(as_uuid=True),
        ForeignKey("script_releases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # How many job changes the run has announced; each event carries
    # the counter's value so watchers can order them and spot gaps.
    event_seq = Column(BigInteger, nullable=False, default=0)
    # Where the run's folder lives on the agent's machine: the path,
    # and the address to rsync it from (none for a laptop or ours).
    folder_path = Column(String(1024), nullable=True)
    folder_address = Column(String(255), nullable=True)
    # When every job reached a final state.
    finished_at = Column(DateTime(timezone=True), nullable=True)
    # The run's zip: none, requested, packing, ready, too_big, failed,
    # expired (see app.runs.bundles).
    bundle_status = Column(String(20), nullable=False, default="none")
    bundle_size = Column(BigInteger, nullable=True)
    bundle_requested_at = Column(DateTime(timezone=True), nullable=True)
    bundle_expires_at = Column(DateTime(timezone=True), nullable=True)
    bundle_error = Column(Text, nullable=True)
