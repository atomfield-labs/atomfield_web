"""
Pydantic schemas for job and pipeline requests and responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobSubmitRequest(BaseModel):
    """
    Payload specification for submitting a standalone simulation job.
    """

    script_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["band_structure.py"],
        description="Name of the simulation script to execute.",
    )
    parameters: dict[str, object] | None = Field(
        default=None,
        examples=[{"lattice_constant_angstrom": 5.43, "temperature_k": 300}],
        description="Input parameters passed to the script.",
    )


class JobResponse(BaseModel):
    """
    Job status and metadata representation model.
    """

    id: UUID
    script_name: str
    status: str
    parameters: dict[str, object] | None = None
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

