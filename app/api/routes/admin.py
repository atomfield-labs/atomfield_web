"""
Administrative API routes for platform monitoring, metrics, and user management.
"""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_owner
from app.api.errors import not_found
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.models.user import User
from app.schemas.auth import (
    AdminQuotaUpdateRequest,
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserSummary,
    JobCounts,
    account_view,
)
from app.services.job_stats import job_counts, job_counts_by_owner

router = APIRouter(prefix="/admin", tags=["Administration"])
USER_KIND = "User"


async def first_key_prefixes(
    db: AsyncSession, *conditions: ColumnElement[bool]
) -> dict[uuid.UUID, str]:
    """
    The start of each person's oldest key, to tell people apart.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param conditions: Which keys, if not every person's.
    :type conditions: ColumnElement[bool]
    :return: Person's id -> key prefix; people without keys are absent.
    :rtype: dict[uuid.UUID, str]
    """
    query = (
        select(ApiKey.user_id, ApiKey.key_prefix)
        .where(*conditions)
        .order_by(ApiKey.user_id, ApiKey.created_at)
        .ext(distinct_on(ApiKey.user_id))
    )
    return dict((await db.execute(query)).all())


def user_summary(
    user: User, key_prefix: str | None, counts: JobCounts
) -> AdminUserSummary:
    """
    One person's account, quota and job counts, as the administrator
    sees them.

    :param user: The person.
    :type user: User
    :param key_prefix: Start of their oldest key, if any.
    :type key_prefix: str | None
    :param counts: Their jobs, counted.
    :type counts: JobCounts
    :return: The summary.
    :rtype: AdminUserSummary
    """
    summary = account_view(AdminUserSummary, user, key_prefix)
    return summary.model_copy(update=counts.model_dump())


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_platform_stats(
    _owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """
    Job counts and compute time across every person, and how many
    people there are.

    :param _owner: The owner.
    :type _owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Platform-wide summary of users, jobs, and execution runtime.
    :rtype: AdminStatsResponse
    """
    users = (await db.execute(select(func.count(User.id)))).scalar_one()
    counts = await job_counts(db)
    return AdminStatsResponse(total_users=users, **counts.model_dump())


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    _owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """
    Every person's account, quota and job counts, newest first.

    :param _owner: The owner.
    :type _owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The people and how many there are.
    :rtype: AdminUserListResponse
    """
    newest_first = select(User).order_by(User.created_at.desc())
    people = (await db.execute(newest_first)).scalars()
    prefixes = await first_key_prefixes(db)
    counts = await job_counts_by_owner(db)
    users = [
        user_summary(
            user, prefixes.get(user.id), counts.get(user.id, JobCounts())
        )
        for user in people
    ]
    return AdminUserListResponse(users=users, total=len(users))


@router.patch("/users/{user_id}/quota", response_model=AdminUserSummary)
async def update_user_quota(
    user_id: UUID,
    payload: AdminQuotaUpdateRequest,
    _owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> AdminUserSummary:
    """
    Update a person's quota limit, or reset what they have used.

    :param user_id: The person.
    :type user_id: UUID
    :param payload: Desired quota adjustments.
    :type payload: AdminQuotaUpdateRequest
    :param _owner: The owner.
    :type _owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Updated user summary representation.
    :rtype: AdminUserSummary
    :raises HTTPException: 404 if no such person.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise not_found(USER_KIND, user_id)
    if payload.quota_limit is not None:
        user.quota_limit = payload.quota_limit
    if payload.reset_quota_used:
        user.quota_used = 0
    await db.commit()
    counts = await job_counts(db, Job.owner_id == user.id)
    prefixes = await first_key_prefixes(db, ApiKey.user_id == user.id)
    return user_summary(user, prefixes.get(user.id), counts)
