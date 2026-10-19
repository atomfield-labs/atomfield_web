"""
HTTP route handlers for API key issuance, identity, and usage analytics.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_api_key, get_optional_api_key
from app.core.config import settings
from app.core.security import generate_api_key, hash_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfoResponse,
    UserStatsResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreateResponse:
    """
    Issue a new cryptographically generated API key with isolated quotas.

    :param request: Creation payload with optional laboratory or user label.
    :type request: ApiKeyCreateRequest
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Full secret key token (shown once) and public prefix metadata.
    :rtype: ApiKeyCreateResponse
    """
    raw_key, display_prefix, key_hash = generate_api_key()
    new_key_record = ApiKey(
        key_hash=key_hash,
        key_prefix=display_prefix,
        label=request.label,
        quota_limit=100,
        quota_used=0,
        is_active=True,
    )
    db.add(new_key_record)
    await db.commit()
    await db.refresh(new_key_record)

    return ApiKeyCreateResponse(
        api_key=raw_key,
        key_prefix=new_key_record.key_prefix,
        label=new_key_record.label,
        quota_limit=new_key_record.quota_limit,
        quota_used=new_key_record.quota_used,
    )


@router.get("/me", response_model=ApiKeyInfoResponse)
async def get_current_user_info(
    api_key: ApiKey = Depends(get_current_api_key),
) -> ApiKeyInfoResponse:
    """
    Fetch identity metadata and calculation quotas for authenticated key.

    :param api_key: Authenticated ApiKey entity resolved from header.
    :type api_key: ApiKey
    :return: User account identity and remaining calculation balance.
    :rtype: ApiKeyInfoResponse
    """
    admin_hash = (
        hash_api_key(settings.ADMIN_API_KEY) if settings.ADMIN_API_KEY else None
    )
    is_admin = bool(admin_hash and api_key.key_hash == admin_hash)
    remaining = max(0, api_key.quota_limit - api_key.quota_used)
    return ApiKeyInfoResponse(
        key_prefix=api_key.key_prefix,
        label=api_key.label,
        quota_limit=api_key.quota_limit,
        quota_used=api_key.quota_used,
        quota_remaining=remaining,
        is_active=api_key.is_active,
        is_admin=is_admin,
    )


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_statistics(
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """
    Aggregate calculation statistics and failure breakdowns for current user.

    :param api_key: Authenticated ApiKey entity resolved from header.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Comprehensive execution metrics dictionary.
    :rtype: UserStatsResponse
    """
    status_query = (
        select(Job.status, func.count(Job.id))
        .where(Job.api_key_id == api_key.id)
        .group_by(Job.status)
    )
    result = await db.execute(status_query)
    status_counts = dict(result.all())

    total = sum(status_counts.values())
    success = status_counts.get("Success", 0)
    failed = status_counts.get("Failed", 0)
    running = status_counts.get("Running", 0)
    pending = status_counts.get("Pending", 0) + status_counts.get("Blocked", 0)
    remaining = max(0, api_key.quota_limit - api_key.quota_used)

    return UserStatsResponse(
        key_prefix=api_key.key_prefix,
        label=api_key.label,
        quota_limit=api_key.quota_limit,
        quota_used=api_key.quota_used,
        quota_remaining=remaining,
        total_jobs=total,
        success_jobs=success,
        failed_jobs=failed,
        running_jobs=running,
        pending_jobs=pending,
    )


@router.get("/quota")
async def get_quota_balance(
    api_key: ApiKey | None = Depends(get_optional_api_key),
) -> dict[str, int]:
    """
    Retrieve real-time remaining quota for client header status pills.

    :param api_key: Optional authenticated ApiKey entity.
    :type api_key: Optional[ApiKey]
    :return: Dictionary containing runsRemaining execution balance.
    :rtype: dict[str, int]
    """
    if not api_key:
        return {"runsRemaining": 100}
    remaining = max(0, api_key.quota_limit - api_key.quota_used)
    return {"runsRemaining": remaining}
