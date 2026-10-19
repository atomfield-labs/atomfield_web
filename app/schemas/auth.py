from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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


class ApiKeyCreateResponse(BaseModel):
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
    key_prefix: str = Field(..., description="Truncated key identifier.")
    label: str | None = Field(default=None, description="Assigned label.")
    quota_limit: int = Field(default=100, description="Max calculation quota.")
    quota_used: int = Field(default=0, description="Allocated calculations.")


class ApiKeyInfoResponse(BaseModel):
    """
    Metadata representation of an authenticated user API key.
    """

    key_prefix: str
    label: str | None = None
    quota_limit: int
    quota_used: int
    quota_remaining: int
    is_active: bool
    is_admin: bool = False


class UserStatsResponse(BaseModel):
    """
    Detailed calculation execution metrics and quotas for an API key holder.
    """

    key_prefix: str
    label: str | None = None
    quota_limit: int
    quota_used: int
    quota_remaining: int
    total_jobs: int
    success_jobs: int
    failed_jobs: int
    running_jobs: int
    pending_jobs: int


class AdminStatsResponse(BaseModel):
    """
    Cluster-wide statistics aggregated across all registered users and jobs.
    """

    total_users: int
    total_jobs: int
    success_jobs: int
    failed_jobs: int
    running_jobs: int
    total_compute_seconds: float


class AdminUserSummary(BaseModel):
    """
    Per-user compute usage summary and quota details for administrators.
    """

    id: UUID
    key_prefix: str
    label: str | None = None
    quota_limit: int
    quota_used: int
    quota_remaining: int
    total_jobs: int
    success_jobs: int
    failed_jobs: int
    running_jobs: int
    total_compute_seconds: float
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
