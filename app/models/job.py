"""
SQLAlchemy ORM models for simulation jobs and DAG dependencies.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base
from app.runs.states import JobStatus


class JobDependency(Base):
    """
    Junction table for DAG directed edges: upstream_id -> downstream_id.
    """

    __tablename__ = "job_dependencies"

    upstream_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    downstream_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )


class Job(Base):
    """
    Represents an individual computational simulation task or pipeline node.
    """

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_name = Column(String(255), nullable=False, index=True)
    status = Column(
        String(50),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Parents not yet succeeded; the job is queued when this reaches 0.
    pending_parents = Column(Integer, nullable=False, default=0)

    # Lease: which agent holds the job, on which attempt, until when.
    attempt = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("compute_targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)

    parameters = Column(JSONB, nullable=True)
    # Input port name -> file names in the session workspace.
    input_files = Column(JSONB, nullable=True)
    output_data = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    api_key_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    execution_time_seconds = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        """
        Produce concise string representation for debugging and logging.

        :return: Human-readable job identifier and status summary.
        :rtype: str
        """
        short_id = str(self.id)[:8] if self.id else "new"
        return f"<Job {short_id} {self.script_name} [{self.status}]>"
