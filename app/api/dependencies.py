"""
Shared FastAPI route dependencies for database, cache, and authentication.
"""

from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.catalog import Catalog
from app.core.config import settings
from app.core.rate_limit import FixedWindowRateLimiter, RateLimit
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.queue.job_queue import RedisJobQueue

CLOUDFLARE_CLIENT_HEADER = "CF-Connecting-IP"
UNKNOWN_CLIENT = "unknown"
SECONDS_PER_HOUR = 3600


async def get_redis(request: Request) -> Redis:
    """
    Provide the Redis client created at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Shared Redis client.
    :rtype: Redis
    """
    return request.app.state.redis


async def get_job_queue(request: Request) -> RedisJobQueue:
    """
    Provide the job queue created at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Shared job queue.
    :rtype: RedisJobQueue
    """
    return request.app.state.job_queue


async def get_catalog(request: Request) -> Catalog:
    """
    Provide the task catalog loaded at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Loaded task catalog.
    :rtype: Catalog
    """
    return request.app.state.catalog


async def get_current_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """
    Authenticate client request via SHA-256 hashed X-API-Key header.

    :param x_api_key: Secret API token provided in HTTP request header.
    :type x_api_key: Optional[str]
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Validated and active ApiKey entity.
    :rtype: ApiKey
    :raises HTTPException: 401 if key is missing, invalid, or inactive.
    """
    if not x_api_key:
        error_msg = (
            "API key required. Please provide a valid 'X-API-Key' header."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg,
        )

    key_hash = hash_api_key(x_api_key)
    query = select(ApiKey).where(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active.is_(True),
    )
    result = await db.execute(query)
    api_key = result.scalars().first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated API key.",
        )

    # Touch last_used_at timestamp asynchronously
    touch_stmt = (
        update(ApiKey)
        .where(ApiKey.id == api_key.id)
        .values(last_used_at=func.now())
    )
    await db.execute(touch_stmt)
    await db.commit()

    return api_key


async def get_optional_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey | None:
    """
    Optionally resolve authenticated API key without enforcing rejection.

    :param x_api_key: Optional API token from header.
    :type x_api_key: Optional[str]
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Resolved ApiKey if present and valid, else None.
    :rtype: Optional[ApiKey]
    """
    if not x_api_key:
        return None
    try:
        return await get_current_api_key(x_api_key=x_api_key, db=db)
    except HTTPException:
        return None


async def require_admin_key(
    api_key: ApiKey = Depends(get_current_api_key),
) -> ApiKey:
    """
    Ensure the calling client holds cluster administrator credentials.

    :param api_key: Authenticated ApiKey entity from request header.
    :type api_key: ApiKey
    :return: Validated administrator ApiKey entity.
    :rtype: ApiKey
    :raises HTTPException: 403 if admin key unconfigured or caller lacks rights.
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key is not configured on the server.",
        )

    if not is_admin_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )

    return api_key


def is_admin_key(api_key: ApiKey) -> bool:
    """
    Decide whether a key is the configured administrator key.

    :param api_key: Authenticated key.
    :type api_key: ApiKey
    :return: True only if an admin key is configured and this is it.
    :rtype: bool
    """
    if not settings.ADMIN_API_KEY:
        return False
    return api_key.key_hash == hash_api_key(settings.ADMIN_API_KEY)


async def get_owned_job(
    job_id: UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Job:
    """
    Load a job the caller may see: their own, or any job for the admin.

    Unknown and foreign jobs both answer 404, so a stranger cannot even
    learn that a job id exists.

    :param job_id: Job id from the URL path.
    :type job_id: UUID
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The job, if the caller may access it.
    :rtype: Job
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    job = await db.get(Job, job_id)
    visible = job is not None and (
        job.api_key_id == api_key.id or is_admin_key(api_key)
    )
    if not visible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return job


def client_address(request: Request) -> str:
    """
    Identify the client for rate limiting.

    Behind Cloudflare Tunnel every request arrives from the tunnel, so
    the real address is in ``CF-Connecting-IP``. That header is trusted
    only when configured, because a direct caller could forge it.

    :param request: Incoming request.
    :type request: Request
    :return: Best-known client address.
    :rtype: str
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get(CLOUDFLARE_CLIENT_HEADER)
        if forwarded:
            return forwarded
    return request.client.host if request.client else UNKNOWN_CLIENT


async def limit_key_creation(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> None:
    """
    Refuse key creation beyond the hourly limit per client address.

    Without it anyone could mint unlimited keys, each with its own job
    quota, which makes the quota meaningless.

    :param request: Incoming request.
    :type request: Request
    :param redis: Shared Redis client holding the counters.
    :type redis: Redis
    :raises HTTPException: 429 with Retry-After when over the limit.
    """
    limit = RateLimit(
        name="api-key-creation",
        max_requests=settings.KEY_CREATION_LIMIT_PER_HOUR,
        window_seconds=SECONDS_PER_HOUR,
    )
    limiter = FixedWindowRateLimiter(redis, limit)
    decision = await limiter.check(client_address(request))
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many new API keys from this address. Try later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
