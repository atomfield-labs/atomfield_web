"""
Schemas for compute targets: the machines (a cluster, a computer) a
user's runs can execute on.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# "slurm": a cluster's login node hands jobs to Slurm.
# "local": the agent runs jobs as its own processes (a laptop).
TargetKind = Literal["slurm", "local"]


class TargetCreate(BaseModel):
    """
    A new place to run jobs.
    """

    name: str = Field(min_length=1, max_length=100)
    kind: TargetKind = "slurm"


class TargetInfo(BaseModel):
    """
    One place the caller can run jobs.
    """

    id: UUID
    name: str
    kind: str
    # The AtomField server, open to everyone; the rest are the caller's.
    shared: bool
    last_seen_at: datetime | None = None
    # Its agent has called in within the last minute and a half.
    online: bool


class TargetToken(BaseModel):
    """
    A target with its agent token. The token is shown this once; only
    its hash is stored.
    """

    target: TargetInfo
    token: str
