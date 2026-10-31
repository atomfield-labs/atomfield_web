"""
Request and response bodies for labs and the people in them.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.user import NAME_LENGTH, Role

# How many people one request may add.
MAX_PEOPLE_AT_ONCE = 100
LabName = Field(min_length=1, max_length=NAME_LENGTH)


class LabCreate(BaseModel):
    """
    A new lab, and the person who will run it.
    """

    name: str = LabName
    admin_email: str


class LabChange(BaseModel):
    """
    What the owner changes about a lab; what is left out stays.
    """

    name: str | None = Field(default=None, min_length=1, max_length=NAME_LENGTH)
    workflows: list[str] | None = None


class PeopleAdd(BaseModel):
    """
    People to put in a lab, by their email.
    """

    emails: list[str] = Field(min_length=1, max_length=MAX_PEOPLE_AT_ONCE)


class PersonChange(BaseModel):
    """
    What changes about a person in a lab; what is left out stays.
    """

    workflows: list[str] | None = None
    role: Literal["admin", "user"] | None = None


class WorkflowName(BaseModel):
    """
    A workflow, as a lab's page names it.
    """

    id: str
    title: str


class LabSummary(BaseModel):
    """
    One lab, as the owner's list shows it.
    """

    id: UUID
    name: str
    workflows: list[WorkflowName]
    people: int


class LabPerson(BaseModel):
    """
    One person in a lab, and what is ticked for them.
    """

    id: UUID
    email: str | None
    name: str | None
    role: Role
    workflows: list[str]
    last_seen_at: datetime | None


class LabDetail(BaseModel):
    """
    One lab, as those who run it see it.
    """

    id: UUID
    name: str
    # What the lab has, and what the one asking could give it.
    workflows: list[WorkflowName]
    available: list[WorkflowName]
    people: list[LabPerson]
