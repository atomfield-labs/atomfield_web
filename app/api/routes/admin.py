"""
Administrative API routes for platform monitoring, metrics, and user management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.schemas.auth import (
    AdminQuotaUpdateRequest,
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserSummary,
)

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_platform_stats(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """
    Aggregate cluster-wide platform execution statistics across all users.

    :param _admin: Authenticated cluster administrator API key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Platform-wide summary of users, jobs, and execution runtime.
    :rtype: AdminStatsResponse
    """
    total_users_query = select(func.count(ApiKey.id))
    total_jobs_query = select(
        func.count(Job.id).label("total"),
        func.sum(case((Job.status == "Success", 1), else_=0)).label("success"),
        func.sum(case((Job.status == "Failed", 1), else_=0)).label("failed"),
        func.sum(case((Job.status == "Running", 1), else_=0)).label("running"),
        func.coalesce(func.sum(Job.execution_time_seconds), 0.0).label(
            "compute_time"
        ),
    )

    users_res = await db.execute(total_users_query)
    total_users = users_res.scalar_one_or_none() or 0

    jobs_res = await db.execute(total_jobs_query)
    row = jobs_res.one_or_none()

    total_jobs = row.total if row else 0
    success_jobs = row.success if row and row.success else 0
    failed_jobs = row.failed if row and row.failed else 0
    running_jobs = row.running if row and row.running else 0
    total_compute_seconds = float(row.compute_time if row else 0.0)

    return AdminStatsResponse(
        total_users=total_users,
        total_jobs=total_jobs,
        success_jobs=success_jobs,
        failed_jobs=failed_jobs,
        running_jobs=running_jobs,
        total_compute_seconds=total_compute_seconds,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """
    Fetch comprehensive calculation metrics and quota usage for all users.

    :param _admin: Authenticated cluster administrator API key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Paginated or full list of users with usage breakdowns.
    :rtype: AdminUserListResponse
    """
    users_stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
    users_res = await db.execute(users_stmt)
    all_keys = list(users_res.scalars().all())

    # Aggregate job metrics grouped by api_key_id
    stats_stmt = (
        select(
            Job.api_key_id,
            func.count(Job.id).label("total_jobs"),
            func.sum(case((Job.status == "Success", 1), else_=0)).label(
                "success_jobs"
            ),
            func.sum(case((Job.status == "Failed", 1), else_=0)).label(
                "failed_jobs"
            ),
            func.sum(case((Job.status == "Running", 1), else_=0)).label(
                "running_jobs"
            ),
            func.coalesce(func.sum(Job.execution_time_seconds), 0.0).label(
                "compute_time"
            ),
        )
        .where(Job.api_key_id.is_not(None))
        .group_by(Job.api_key_id)
    )
    stats_res = await db.execute(stats_stmt)
    stats_map = {row.api_key_id: row for row in stats_res.all()}

    user_summaries: list[AdminUserSummary] = []
    for key in all_keys:
        st = stats_map.get(key.id)
        tot_jobs = st.total_jobs if st else 0
        succ_jobs = st.success_jobs if st and st.success_jobs else 0
        fail_jobs = st.failed_jobs if st and st.failed_jobs else 0
        run_jobs = st.running_jobs if st and st.running_jobs else 0
        compute_sec = float(st.compute_time if st else 0.0)
        remaining = max(0, key.quota_limit - key.quota_used)

        user_summaries.append(
            AdminUserSummary(
                id=key.id,
                key_prefix=key.key_prefix,
                label=key.label,
                quota_limit=key.quota_limit,
                quota_used=key.quota_used,
                quota_remaining=remaining,
                total_jobs=tot_jobs,
                success_jobs=succ_jobs,
                failed_jobs=fail_jobs,
                running_jobs=run_jobs,
                total_compute_seconds=compute_sec,
                is_active=key.is_active,
                created_at=key.created_at,
                last_used_at=key.last_used_at,
            )
        )

    return AdminUserListResponse(
        users=user_summaries,
        total=len(user_summaries),
    )


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
    key_stmt = select(ApiKey).where(ApiKey.id == user_id)
    key_res = await db.execute(key_stmt)
    key = key_res.scalars().first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User key {user_id} not found.",
        )

    if payload.quota_limit is not None:
        key.quota_limit = payload.quota_limit
    if payload.reset_quota_used:
        key.quota_used = 0

    await db.commit()
    await db.refresh(key)

    # Re-calculate job statistics
    stats_stmt = select(
        func.count(Job.id).label("total_jobs"),
        func.sum(case((Job.status == "Success", 1), else_=0)).label(
            "success_jobs"
        ),
        func.sum(case((Job.status == "Failed", 1), else_=0)).label(
            "failed_jobs"
        ),
        func.sum(case((Job.status == "Running", 1), else_=0)).label(
            "running_jobs"
        ),
        func.coalesce(func.sum(Job.execution_time_seconds), 0.0).label(
            "compute_time"
        ),
    ).where(Job.api_key_id == key.id)
    stats_res = await db.execute(stats_stmt)
    st = stats_res.one_or_none()

    tot_jobs = st.total_jobs if st else 0
    succ_jobs = st.success_jobs if st and st.success_jobs else 0
    fail_jobs = st.failed_jobs if st and st.failed_jobs else 0
    run_jobs = st.running_jobs if st and st.running_jobs else 0
    compute_sec = float(st.compute_time if st else 0.0)
    remaining = max(0, key.quota_limit - key.quota_used)

    return AdminUserSummary(
        id=key.id,
        key_prefix=key.key_prefix,
        label=key.label,
        quota_limit=key.quota_limit,
        quota_used=key.quota_used,
        quota_remaining=remaining,
        total_jobs=tot_jobs,
        success_jobs=succ_jobs,
        failed_jobs=fail_jobs,
        running_jobs=run_jobs,
        total_compute_seconds=compute_sec,
        is_active=key.is_active,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
    )
