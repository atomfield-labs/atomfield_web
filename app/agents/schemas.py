"""
Request and response bodies of the agent API.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.catalog.models import TaskDefinition

MAX_CLAIM_WAIT_SECONDS = 30.0
# Small files the UI shows, uploaded when a job ends: how many, and
# how big each may be (a longer log is sent as its last part).
MAX_UI_FILES = 20
UI_FILE_MAX_BYTES = 2 * 1024 * 1024
# The command's own output, written by the agent into every job folder.
EXECUTION_LOG = "execution.log"


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


class InputFile(BaseModel):
    """
    One input file and a signed link to download it.
    """

    name: str
    url: str


class JobAssignment(BaseModel):
    """
    Everything an agent needs to run one attempt of a job.
    """

    job_id: uuid.UUID
    attempt: int
    run_id: uuid.UUID
    node_key: str = Field(
        description="The job's folder name, unique within its run.",
    )
    parents: list[str] = Field(
        default_factory=list,
        description="Node keys of the parents. One run runs on one "
        "machine, so their folders sit beside this job's.",
    )
    task: TaskDefinition
    parameters: dict[str, Any]
    input_files: dict[str, list[str]]
    inputs: list[InputFile] = Field(
        default_factory=list,
        description="Files to download into the job's folder first.",
    )
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


class PackRequest(BaseModel):
    """
    "Zip this run's folder and upload it here."
    """

    run_id: uuid.UUID
    bundle_name: str = Field(
        description="Folder name inside the zip (also the file name).",
    )
    upload_url: str
    max_bytes: int
    manifest: dict[str, Any] = Field(
        description="Written into the zip as run.json: every job, its "
        "status, parameters and files, including jobs that never ran.",
    )


class BundleReport(BaseModel):
    """
    How packing a run ended.
    """

    status: Literal["ready", "too_big", "failed"]
    size_bytes: int | None = None
    error: str | None = None


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
    pack: list[PackRequest] = Field(
        default_factory=list,
        description="Runs to zip and upload.",
    )


class FileCard(BaseModel):
    """
    One file a job left in its folder.
    """

    path: str = Field(description="Relative to the job's folder.")
    size_bytes: int
    sha256: str
    uploaded: bool = Field(
        default=False,
        description="A copy is in the store (small files the UI shows; "
        "a long log is sent as its end).",
    )


class FolderLocation(BaseModel):
    """
    Where a run's folder lives on the agent's machine.
    """

    path: str
    address: str | None = Field(
        default=None,
        description="What to type before ':' in rsync or scp, such as "
        "you@login.hpc.edu; none for a laptop or the house agent.",
    )


class UploadLinksRequest(BaseModel):
    """
    An agent asking where to upload a finished job's small files.
    """

    attempt: int
    names: list[str] = Field(max_length=MAX_UI_FILES)


class UploadLinksResponse(BaseModel):
    """
    One upload link per file name, each accepting ``max_bytes``.
    """

    links: dict[str, str]
    max_bytes: int


class CompletionRequest(BaseModel):
    """
    How one attempt ended.
    """

    attempt: int
    outcome: Literal["succeeded", "failed", "cancelled"]
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    execution_time_seconds: float | None = None
    files: list[FileCard] = Field(default_factory=list)
    folder: FolderLocation | None = None


class CompletionResponse(BaseModel):
    """
    The recorded outcome.
    """

    job_id: uuid.UUID
    status: str
    children_queued: int
    pack: list[PackRequest] = Field(
        default_factory=list,
        description="Runs to zip and upload (this report may have "
        "finished one).",
    )
