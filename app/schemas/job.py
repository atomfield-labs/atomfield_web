"""
Pydantic schemas for job and pipeline requests and responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import FieldInfo

InputFiles = dict[str, list[str]]


def input_files_field() -> FieldInfo:
    """
    Describe the input-file mapping shared by job and node requests.

    :return: Pydantic field defaulting to no input files.
    :rtype: FieldInfo
    """
    return Field(
        default_factory=dict,
        examples=[{"structure": ["water.xyz"]}],
        description=(
            "Input port name -> uploaded file names. Ports and formats "
            "are listed by GET /api/task-definitions."
        ),
    )


class JobSubmitRequest(BaseModel):
    """
    Payload specification for submitting a standalone simulation job.
    """

    script_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["xtb_opt"],
        description="Id of a task from GET /api/task-definitions.",
    )
    parameters: dict[str, object] | None = Field(
        default=None,
        examples=[{"charge": 0, "optlevel": "tight"}],
        description="Values for the task's parameters; omitted ones use "
        "their defaults.",
    )
    inputs: InputFiles = input_files_field()


class JobResponse(BaseModel):
    """
    Job status and metadata representation model.
    """

    id: UUID
    run_id: UUID
    script_name: str
    status: str
    parameters: dict[str, object] | None = None
    input_files: InputFiles | None = None
    output_data: dict[str, object] | None = None
    error_message: str | None = None
    execution_time_seconds: float | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    """
    Paginated collection of simulation jobs.
    """

    jobs: list[JobResponse]
    total: int


class JobNode(BaseModel):
    """
    Frontend DAG node definition schema.
    """

    ui_id: str = Field(
        ...,
        description=(
            "Temporary frontend node ID linking edges before DB insertion."
        ),
    )
    script_name: str = Field(..., min_length=1, max_length=255)
    parameters: dict[str, object] = Field(default_factory=dict)
    inputs: InputFiles = input_files_field()


class JobEdge(BaseModel):
    """
    Directed dependency link connecting upstream to downstream node.
    """

    upstream_ui_id: str
    downstream_ui_id: str


class PipelineFile(BaseModel):
    """
    File attachment uploaded alongside a DAG pipeline submission.
    """

    filename: str
    content: str


class PipelineSubmitRequest(BaseModel):
    """
    Request payload specification for submitting a DAG pipeline.
    """

    session_id: str | None = None
    nodes: list[JobNode]
    edges: list[JobEdge]
    files: list[PipelineFile] | None = None


class PipelineSubmitResponse(BaseModel):
    """
    Response payload returned upon DAG pipeline submission.
    """

    status: str
    total_nodes: int
    roots_started: int
    pipeline_id: str | None = None
    run_id: UUID | None = None
    job_ids: dict[str, str] = Field(default_factory=dict)


class TextArtifactItem(BaseModel):
    """
    Individual text-based artifact file representation.
    """

    filename: str
    content: str
    size_bytes: int


class TextArtifactsResponse(BaseModel):
    """
    Collection of readable text artifacts for a completed job or session.
    """

    session_id: str | None = None
    job_id: str | None = None
    files: list[TextArtifactItem] = Field(default_factory=list)
