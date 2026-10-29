"""
Request and response bodies for keys, quotas and job statistics.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.api_key import DEFAULT_QUOTA_LIMIT


class ApiKeyCreateRequest(BaseModel):
    """
    Request payload for registering a new user API key.
    """

    label: str | None = Field(
        default=None,
        max_length=100,
        examples=["Dr. Miller - Organic Synthesis Lab"],
        description="Optional human-friendly identity or laboratory label.",
    )


class KeyQuota(BaseModel):
    """
    A key as its holder knows it, and its quota; read straight from the
    stored key.
    """

    model_config = ConfigDict(from_attributes=True)

    key_prefix: str = Field(..., description="Truncated key identifier.")
    label: str | None = Field(default=None, description="Assigned label.")
    quota_limit: int = Field(
        default=DEFAULT_QUOTA_LIMIT, description="Max calculation quota."
    )
    quota_used: int = Field(default=0, description="Allocated calculations.")
    quota_remaining: int = Field(..., description="Calculations left.")


class JobCounts(BaseModel):
    """
    How many jobs are in each kind of state, and the compute time they
    used.
    """

    total_jobs: int = 0
    success_jobs: int = 0
    failed_jobs: int = 0
    running_jobs: int = 0
    pending_jobs: int = 0
    total_compute_seconds: float = 0.0


class ApiKeyCreateResponse(KeyQuota):
    """
    Response payload returned upon generating a new API key.
    """

    api_key: str = Field(
        ...,
        description=(
            "Full secret API key. Store this securely; it will not be shown "
            "again."
        ),
    )


class ApiKeyInfoResponse(KeyQuota):
    """
    Metadata representation of an authenticated user API key.
    """

    is_active: bool
    is_admin: bool = False


class UserStatsResponse(KeyQuota, JobCounts):
    """
    A key holder's quota and job counts.
    """


class AdminStatsResponse(JobCounts):
    """
    Job counts across every user, and how many users there are.
    """

    total_users: int


class AdminUserSummary(KeyQuota, JobCounts):
    """
    One user's key, quota and job counts, for the administrator.
    """

    id: UUID
    is_active: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class AdminUserListResponse(BaseModel):
    """
    Paginated or full list response of all cluster users and usage metrics.
    """

    users: list[AdminUserSummary]
    total: int


class AdminQuotaUpdateRequest(BaseModel):
    """
    Payload for administrator updates to a user's compute quota.
    """

    quota_limit: int | None = Field(
        default=None,
        ge=0,
        description="Updated maximum calculation quota.",
    )
    reset_quota_used: bool = Field(
        default=False,
        description="Whether to reset the allocated calculation counter to 0.",
    )
