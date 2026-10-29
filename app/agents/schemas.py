"""
Request and response bodies of the agent API.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, Field

from app.catalog.models import TaskDefinition
from app.core.names import version_label
from app.runs.states import JobStatus

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
    scheduled: bool = Field(
        default=False,
        description="This agent hands jobs to a scheduler (Slurm): they "
        "may wait in its queue, so their clock starts only when the "
        "agent reports them started.",
    )


class InputFile(BaseModel):
    """
    One input file and a signed link to download it.
    """

    name: str
    url: str


class ArchiveRef(BaseModel):
    """
    A zip file an agent downloads once and keeps: its name, version and
    fingerprint, and a signed link to it.
    """

    name: str
    version: str
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Fingerprint the downloaded file must match.",
    )
    url: str

    @property
    def label(self) -> str:
        """
        How people see the archive.

        :return: Its name and version.
        :rtype: str
        """
        return version_label(self.name, self.version)


class ReleaseRef(ArchiveRef):
    """
    The scripts release a job runs (a wheel).
    """


class DataRef(ArchiveRef):
    """
    A data pack a job reads, and the environment variable that gets
    its folder.
    """

    env: str


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
    release: ReleaseRef | None = Field(
        default=None,
        description="The scripts to run; none for a run from before the "
        "first release (the agent then needs its own copy).",
    )
    data: list[DataRef] = Field(
        default_factory=list,
        description="Data packs to have in place before the job starts.",
    )
    deadline_at: datetime | None = Field(
        default=None,
        description="When the job must be done; none for a job handed "
        "to a scheduler, which enforces the time limit itself.",
    )


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
    started: list[JobReference] = Field(
        default_factory=list,
        description="Attempts that have begun running (not merely "
        "waiting in a scheduler's queue).",
    )


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


class PackOutcome(StrEnum):
    """
    How packing a run's zip ended, as its agent reports it.
    """

    READY = "ready"
    TOO_BIG = "too_big"
    FAILED = "failed"


class BundleReport(BaseModel):
    """
    How packing a run ended.
    """

    status: PackOutcome
    size_bytes: int | None = None
    error: str | None = None

    @classmethod
    def ready(cls, size_bytes: int) -> Self:
        """
        The zip was uploaded.

        :param size_bytes: Its size.
        :type size_bytes: int
        :return: The report.
        :rtype: BundleReport
        """
        return cls(status=PackOutcome.READY, size_bytes=size_bytes)

    @classmethod
    def too_big(cls, size_bytes: int) -> Self:
        """
        The zip passed the size the server, or a proxy before it,
        accepts; the run's folder stays where it is.

        :param size_bytes: Size reached.
        :type size_bytes: int
        :return: The report.
        :rtype: BundleReport
        """
        return cls(status=PackOutcome.TOO_BIG, size_bytes=size_bytes)

    @classmethod
    def failed(cls, error: str) -> Self:
        """
        Packing failed.

        :param error: Why, for the user.
        :type error: str
        :return: The report.
        :rtype: BundleReport
        """
        return cls(status=PackOutcome.FAILED, error=error)


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
    outcome: Literal[JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]
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
