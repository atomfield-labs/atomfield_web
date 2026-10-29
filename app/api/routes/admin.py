"""
Administrative API routes for platform monitoring, metrics, and user management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin_key
from app.api.errors import not_found
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.schemas.auth import (
    AdminQuotaUpdateRequest,
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserSummary,
    JobCounts,
)
from app.services.job_stats import job_counts, job_counts_by_owner

router = APIRouter(prefix="/admin", tags=["Administration"])
USER_KIND = "User key"


def user_summary(key: ApiKey, counts: JobCounts) -> AdminUserSummary:
    """
    One user's key, quota and job counts, as the administrator sees
    them.

    :param key: The user's key.
    :type key: ApiKey
    :param counts: Their jobs, counted.
    :type counts: JobCounts
    :return: The summary.
    :rtype: AdminUserSummary
    """
    summary = AdminUserSummary.model_validate(key)
    return summary.model_copy(update=counts.model_dump())


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_platform_stats(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """
    Job counts and compute time across every user, and how many users
    there are.

    :param _admin: Authenticated cluster administrator API key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Platform-wide summary of users, jobs, and execution runtime.
    :rtype: AdminStatsResponse
    """
    users = (await db.execute(select(func.count(ApiKey.id)))).scalar_one()
    counts = await job_counts(db)
    return AdminStatsResponse(total_users=users, **counts.model_dump())


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """
    Every user's key, quota and job counts, newest key first.

    :param _admin: Authenticated cluster administrator API key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The users and how many there are.
    :rtype: AdminUserListResponse
    """
    newest_first = select(ApiKey).order_by(ApiKey.created_at.desc())
    keys = (await db.execute(newest_first)).scalars()
    counts = await job_counts_by_owner(db)
    users = [user_summary(key, counts.get(key.id, JobCounts())) for key in keys]
    return AdminUserListResponse(users=users, total=len(users))


@router.patch("/users/{user_id}/quota", response_model=AdminUserSummary)
async def update_user_quota(
    user_id: UUID,
    payload: AdminQuotaUpdateRequest,
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> AdminUserSummary:
    """
    Update calculation quota limit or reset quota counter for a user key.

    :param user_id: Unique UUID of the target ApiKey entity.
    :type user_id: UUID
    :param payload: Desired quota adjustments.
    :type payload: AdminQuotaUpdateRequest
    :param _admin: Authenticated cluster administrator API key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Updated user summary representation.
    :rtype: AdminUserSummary
    :raises HTTPException: 404 if user not found.
    """
    key = await db.get(ApiKey, user_id)
    if key is None:
        raise not_found(USER_KIND, user_id)
    if payload.quota_limit is not None:
        key.quota_limit = payload.quota_limit
    if payload.reset_quota_used:
        key.quota_used = 0
    await db.commit()
    counts = await job_counts(db, Job.api_key_id == key.id)
    return user_summary(key, counts)
