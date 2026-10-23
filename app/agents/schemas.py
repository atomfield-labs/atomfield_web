"""
Request and response bodies of the agent API.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.catalog.models import TaskDefinition

MAX_CLAIM_WAIT_SECONDS = 30.0


class ClaimRequest(BaseModel):
    """
    An agent asking for one job.
    """

    wait_seconds: float = Field(
        default=25.0,
        gt=0,
        le=MAX_CLAIM_WAIT_SECONDS,
        description="How long the server may hold the request open "
        "waiting for a job (long polling).",
    )


class JobAssignment(BaseModel):
    """
    Everything an agent needs to run one attempt of a job.
    """

    job_id: uuid.UUID
    attempt: int
    run_id: uuid.UUID
    task: TaskDefinition
    parameters: dict[str, Any]
    input_files: dict[str, list[str]]
    deadline_at: datetime


class JobReference(BaseModel):
    """
    One attempt of one job, as agents and server refer to it.
    """

    job_id: uuid.UUID
    attempt: int


class HeartbeatRequest(BaseModel):
    """
    "I am alive, and these are the attempts I am running."
    """

    jobs: list[JobReference] = Field(default_factory=list)


class HeartbeatResponse(BaseModel):
    """
    What the agent should do about the attempts it reported.
    """

    cancel: list[JobReference] = Field(
        default_factory=list,
        description="Stop these, then report them as cancelled.",
    )
    abandon: list[JobReference] = Field(
        default_factory=list,
        description="No longer yours (finished, or retried elsewhere): "
        "stop them and report nothing.",
    )


class CompletionRequest(BaseModel):
    """
    How one attempt ended.
    """

    attempt: int
    outcome: Literal["succeeded", "failed", "cancelled"]
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    execution_time_seconds: float | None = None


class CompletionResponse(BaseModel):
    """
    The recorded outcome.
    """

    job_id: uuid.UUID
    status: str
    children_queued: int
