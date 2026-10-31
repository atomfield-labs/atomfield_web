"""
Request and response bodies for a person's pipelines.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.user import NAME_LENGTH


class SessionState(StrEnum):
    """
    How a pipeline stands, from its newest run.
    """

    DRAFT = "draft"
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionSave(BaseModel):
    """
    What changed about a pipeline; what is left out stays. An empty
    title makes it untitled again.
    """

    title: str | None = Field(default=None, max_length=NAME_LENGTH)
    blueprint: dict[str, Any] | None = None
    node_count: int | None = Field(default=None, ge=0)


class SessionSummary(BaseModel):
    """
    One pipeline, as the sessions page shows it.
    """

    id: str
    title: str | None
    state: SessionState
    node_count: int
    updated_at: datetime


class SessionDetail(SessionSummary):
    """
    One pipeline, as the editor opens it.
    """

    blueprint: dict[str, Any] | None
    run_id: UUID | None
    job_ids: dict[str, str]
