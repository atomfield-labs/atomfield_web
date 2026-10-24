"""
Schemas for cancelling runs and fetching their results.
"""

from datetime import datetime
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


class FolderInfo(BaseModel):
    """
    Where a run's files stayed: on the machine that ran them.
    """

    path: str
    address: str | None = None
    # Ready to paste, when the machine can be reached by rsync.
    copy_command: str | None = None


class BundleInfo(BaseModel):
    """
    How to get a run's files: a zip download, or where they are.
    """

    run_id: UUID
    finished: bool
    # none, requested, packing, ready, too_big, failed, expired.
    status: str
    size_bytes: int | None = None
    expires_at: datetime | None = None
    # A link valid for a few minutes, when the zip is ready.
    download_url: str | None = None
    error: str | None = None
    folder: FolderInfo | None = None
