"""
SQLAlchemy ORM model for a person's pipelines: what the sessions page
lists and the editor opens.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.identifiers import MAX_IDENTIFIER_LENGTH
from app.db.base import Base
from app.models.user import NAME_LENGTH


class PipelineSession(Base):
    """
    One person's pipeline: its name and draft, and its newest run. The
    web app makes the id, so the person is part of the key: two people's
    can match without either seeing the other's.
    """

    __tablename__ = "pipeline_sessions"

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id = Column(String(MAX_IDENTIFIER_LENGTH), primary_key=True)
    # None until the person or a template names it.
    title = Column(String(NAME_LENGTH), nullable=True)
    # The canvas as the web app saved it; none for a script's run.
    blueprint = Column(JSONB, nullable=True)
    node_count = Column(Integer, nullable=False, default=0)
    # The newest run, and which job each of its nodes became.
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_ids = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs.

        :return: Whose session it is.
        :rtype: str
        """
        return f"<PipelineSession {self.id} of {self.owner_id}>"
