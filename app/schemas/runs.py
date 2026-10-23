"""
Schemas for cancelling jobs and runs.
"""

from uuid import UUID

from pydantic import BaseModel


class JobCancelResponse(BaseModel):
    """
    Result of cancelling one job.
    """

    job_id: UUID
    # "cancelled" (done now) or "cancelling" (its agent was asked).
    status: str


class RunCancelResponse(BaseModel):
    """
    Result of cancelling every unfinished job of a run.
    """

    run_id: UUID
    cancelled: int
    cancelling: int
