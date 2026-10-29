"""
HTTP route handlers for API key issuance, identity, and usage analytics.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_api_key,
    is_admin_key,
    limit_key_creation,
)
from app.core.security import generate_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfoResponse,
    KeyQuota,
    UserStatsResponse,
)
from app.services.job_stats import job_counts

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_key_creation)],
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
    key = ApiKey(
        key_hash=key_hash, key_prefix=display_prefix, label=request.label
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    quota = KeyQuota.model_validate(key).model_dump()
    return ApiKeyCreateResponse(api_key=raw_key, **quota)


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
    info = ApiKeyInfoResponse.model_validate(api_key)
    return info.model_copy(update={"is_admin": is_admin_key(api_key)})


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
    counts = await job_counts(db, Job.api_key_id == api_key.id)
    stats = UserStatsResponse.model_validate(api_key)
    return stats.model_copy(update=counts.model_dump())
