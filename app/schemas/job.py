"""
app/schemas/job.py — Pydantic Validation Schemas

📚 LESSON: The Schema Layer (API Contract)

    Schemas define the SHAPE of data crossing the API boundary.
    They are your firewall between the outside world and your database.

    Key principle: Input schema ≠ Output schema.
    • Input (JobSubmitRequest): only what the client SHOULD provide.
    • Output (JobResponse): only what the client SHOULD see.

    If you later add an internal field (e.g., retry_count), you add it
    to the Model but NOT to the output schema — the client never sees it.

📚 LESSON: Why ConfigDict over class Config?
    Pydantic v1 used `class Config` (inner class). Pydantic v2 uses
    `model_config = ConfigDict(...)` — a typed dict that gives IDE
    autocomplete and catches typos at import time.
    `class Config` still works (backward compat) but is deprecated.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------
# Request Schemas (what comes IN)
# -----------------------------------------------------------------------

class JobSubmitRequest(BaseModel):
    """Client submits this to create a new simulation job."""
    script_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["band_structure.py"],
        description="Name of the simulation script to execute.",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        examples=[{"lattice_constant_angstrom": 5.43, "temperature_k": 300}],
        description="Input parameters passed to the script (XCom input).",
    )


# -----------------------------------------------------------------------
# Response Schemas (what goes OUT)
# -----------------------------------------------------------------------

class JobResponse(BaseModel):
    """Returned to the client after submission or polling."""
    id: UUID
    script_name: str
    status: str
    parameters: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    """Paginated list of jobs — used by GET /jobs."""
    jobs: list[JobResponse]
    total: int

# -----------------------------------------------------------------------
# Pipeline / DAG Schemas
# -----------------------------------------------------------------------

class JobNode(BaseModel):
    ui_id: str = Field(..., description="Temporary frontend ID to link edges before DB creation")
    script_name: str = Field(..., min_length=1, max_length=255)
    parameters: Dict[str, Any] = Field(default_factory=dict)

class JobEdge(BaseModel):
    upstream_ui_id: str
    downstream_ui_id: str

class PipelineSubmitRequest(BaseModel):
    """Client submits this to create a full DAG pipeline of jobs."""
    nodes: list[JobNode]
    edges: list[JobEdge]

class PipelineSubmitResponse(BaseModel):
    status: str
    total_nodes: int
    roots_started: int
