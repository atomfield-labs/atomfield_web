"""
Request and response bodies for keys, quotas and job statistics.
"""

from datetime import datetime
from typing import TypeVar
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.user import DEFAULT_QUOTA_LIMIT, Role, User


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
    A person as the key in use shows them, and their quota; read
    straight from the stored person (``account_view``).
    """

    model_config = ConfigDict(from_attributes=True)

    key_prefix: str | None = Field(
        default=None, description="Start of the key in use."
    )
    label: str | None = Field(
        default=None,
        validation_alias=AliasChoices("label", "name"),
        description="The person's name.",
    )
    email: str | None = Field(
        default=None, description="Their email, once they have signed in."
    )
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


class ApiKeyInfoResponse(KeyQuota):
    """
    Metadata representation of an authenticated user API key.
    """

    is_active: bool
    role: Role = Role.USER
    lab_id: UUID | None = None


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
    role: Role = Role.USER
    lab_id: UUID | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("last_used_at", "last_seen_at"),
    )


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


class ScriptKeyView(BaseModel):
    """
    One of a person's keys as they see it: never the secret itself.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_prefix: str
    label: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class NewScriptKey(ScriptKeyView):
    """
    A key just made, with its secret, which is shown this once.
    """

    api_key: str = Field(
        ..., description="The secret. Store it now; it is not shown again."
    )


AccountView = TypeVar("AccountView", bound=KeyQuota)


def account_view(
    schema: type[AccountView], user: User, key_prefix: str | None
) -> AccountView:
    """
    A response about a person, read from them, showing the key in use.

    :param schema: The response to build.
    :type schema: type[AccountView]
    :param user: The person.
    :type user: User
    :param key_prefix: Start of their key, if one is in use.
    :type key_prefix: str | None
    :return: The response.
    :rtype: AccountView
    """
    view = schema.model_validate(user)
    return view.model_copy(update={"key_prefix": key_prefix})
