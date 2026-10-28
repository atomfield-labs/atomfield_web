"""
Response bodies for script releases.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReleaseInfo(BaseModel):
    """
    A published release of the scripts.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: str
    sha256: str
    git_commit: str | None = None
    published_at: datetime


class DataPackInfo(BaseModel):
    """
    A published data pack.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: str
    sha256: str
    size_bytes: int
    published_at: datetime
