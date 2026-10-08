"""
app/models/job.py — Job ORM Model

📚 LESSON: The Model Layer in DDD (Domain-Driven Design)

    Models represent your DOMAIN ENTITIES — the core "things" your system
    cares about. In AtomField, a Job is the central entity.

    The model knows NOTHING about:
    • HTTP (no Request/Response objects)
    • Business rules (no "if status == X then do Y")
    • Serialization (no JSON encoding)

    It only knows its own columns and relationships. This is the
    "Persistence Ignorance" principle — the model describes the shape
    of the data, not how it's used.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base

class JobDependency(Base):
    """
    Junction table for DAG edges.
    upstream_id -> downstream_id
    """
    __tablename__ = "job_dependencies"

    upstream_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    downstream_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)




class Job(Base):
    __tablename__ = "jobs"

    # -----------------------------------------------------------------------
    # UUID PK: Security over convenience (no IDOR via sequential IDs)
    # -----------------------------------------------------------------------
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Execution Routing ---
    script_name = Column(String(255), nullable=False, index=True)
    status = Column(
        String(50),
        nullable=False,
        default="Pending",
        index=True,  # 📚 Indexed — you'll query "show me all Running jobs" often
    )

    # --- XCom: Cross-Communication Data (Apache Airflow pattern) ---
    parameters = Column(JSONB, nullable=True)    # input to the script
    output_data = Column(JSONB, nullable=True)   # output from the script

    # --- Error Tracking (improvement over plan) ---
    error_message = Column(Text, nullable=True)  # stack trace on failure

    # --- Audit Trail ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        """
        📚 LESSON: Always define __repr__ on ORM models.
        Without it, debugging logs show <Job object at 0x7f...> — useless.
        With it: <Job abc123 sample_script.py [Running]> — instantly useful.
        """
        short_id = str(self.id)[:8] if self.id else "new"
        return f"<Job {short_id} {self.script_name} [{self.status}]>"
