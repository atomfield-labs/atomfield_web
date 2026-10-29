"""
HTTP route handlers for API key issuance, identity, and usage analytics.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Caller, get_caller, limit_key_creation
from app.db.session import get_db
from app.models.job import Job
from app.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfoResponse,
    KeyQuota,
    UserStatsResponse,
    account_view,
)
from app.services.accounts import add_person, new_key
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
    Make a new person and their first API key (shown once); the label
    names both.

    :param request: Creation payload with optional laboratory or user label.
    :type request: ApiKeyCreateRequest
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Full secret key token (shown once) and public prefix metadata.
    :rtype: ApiKeyCreateResponse
    """
    user = await add_person(db, request.label)
    secret, key = new_key(user.id, request.label)
    db.add(key)
    await db.commit()
    await db.refresh(user)
    quota = account_view(KeyQuota, user, key.key_prefix).model_dump()
    return ApiKeyCreateResponse(api_key=secret, **quota)


@router.get("/me", response_model=ApiKeyInfoResponse)
async def get_current_user_info(
    caller: Caller = Depends(get_caller),
) -> ApiKeyInfoResponse:
    """
    Fetch identity metadata and calculation quotas for the caller.

    :param caller: The person, and the key they used.
    :type caller: Caller
    :return: User account identity and remaining calculation balance.
    :rtype: ApiKeyInfoResponse
    """
    prefix = caller.api_key.key_prefix
    return account_view(ApiKeyInfoResponse, caller.user, prefix)


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_statistics(
    caller: Caller = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """
    Aggregate calculation statistics and failure breakdowns for the caller.

    :param caller: The person, and the key they used.
    :type caller: Caller
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Comprehensive execution metrics dictionary.
    :rtype: UserStatsResponse
    """
    counts = await job_counts(db, Job.owner_id == caller.user.id)
    prefix = caller.api_key.key_prefix
    stats = account_view(UserStatsResponse, caller.user, prefix)
    return stats.model_copy(update=counts.model_dump())
