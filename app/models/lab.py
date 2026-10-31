"""
SQLAlchemy ORM models for labs. A person's lab is on the person
(``users.lab_id``); these say which workflows the owner gave a lab, and
which of those its admin gave each person.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.catalog.models import WORKFLOW_ID_LENGTH
from app.db.base import Base
from app.models.user import NAME_LENGTH


class Lab(Base):
    """
    A group of people given workflows together: the unit that pays.
    """

    __tablename__ = "labs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(NAME_LENGTH), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        """
        Produce a short description for debugging and logs.

        :return: The lab's name.
        :rtype: str
        """
        return f"<Lab {self.name}>"


class LabWorkflow(Base):
    """
    A workflow the owner gave a lab.
    """

    __tablename__ = "lab_workflows"

    lab_id = Column(
        UUID(as_uuid=True),
        ForeignKey("labs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_id = Column(String(WORKFLOW_ID_LENGTH), primary_key=True)


class UserWorkflow(Base):
    """
    A workflow a lab's admin gave a person. It counts only while their
    lab still has it, so taking one from a lab takes it from everyone.
    """

    __tablename__ = "user_workflows"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_id = Column(String(WORKFLOW_ID_LENGTH), primary_key=True)
