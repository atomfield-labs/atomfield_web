"""
Shared FastAPI route dependencies for database, cache, and authentication.
"""

from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import not_found, unauthorized
from app.core.config import settings
from app.core.rate_limit import FixedWindowRateLimiter, RateLimit
from app.core.security import hash_api_key
from app.db.session import get_db
from app.events.bus import EventBus
from app.models.api_key import ApiKey
from app.models.job import Job
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import CurrentCatalog, ReleaseCatalogs
from app.storage.store import LocalDiskStore

CLOUDFLARE_CLIENT_HEADER = "CF-Connecting-IP"
UNKNOWN_CLIENT = "unknown"
SECONDS_PER_HOUR = 3600


MISSING_KEY_MESSAGE = (
    "API key required. Please provide a valid 'X-API-Key' header."
)
INVALID_KEY_MESSAGE = "Invalid or deactivated API key."


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


async def get_event_bus(request: Request) -> EventBus:
    """
    Provide the event bus created at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Shared event bus.
    :rtype: EventBus
    """
    return request.app.state.event_bus


async def get_store(request: Request) -> LocalDiskStore:
    """
    Provide the file store created at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Shared store.
    :rtype: LocalDiskStore
    """
    return request.app.state.store


async def get_catalogs(request: Request) -> ReleaseCatalogs:
    """
    Provide the catalog of every release, built on first use.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Catalogs by release.
    :rtype: ReleaseCatalogs
    """
    return request.app.state.catalogs


async def get_current_catalog(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentCatalog:
    """
    Provide the catalog new runs are checked against: the newest
    release's, with that release (new runs are pinned to it).

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The current release and its catalog.
    :rtype: CurrentCatalog
    """
    return await request.app.state.catalogs.current(db)


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
        raise unauthorized(MISSING_KEY_MESSAGE)
    api_key = await active_key(db, x_api_key)
    if api_key is None:
        raise unauthorized(INVALID_KEY_MESSAGE)
    await mark_used(db, api_key)
    return api_key


async def active_key(db: AsyncSession, secret: str) -> ApiKey | None:
    """
    The active key with this secret (keys are stored as hashes).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param secret: The key as the client sent it.
    :type secret: str
    :return: The key, or None if unknown or deactivated.
    :rtype: ApiKey | None
    """
    query = select(ApiKey).where(
        ApiKey.key_hash == hash_api_key(secret),
        ApiKey.is_active.is_(True),
    )
    return (await db.execute(query)).scalars().first()


async def mark_used(db: AsyncSession, api_key: ApiKey) -> None:
    """
    Record when a key was last used.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param api_key: The key.
    :type api_key: ApiKey
    """
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key.id)
        .values(last_used_at=func.now())
    )
    await db.commit()


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


def may_act_on(api_key: ApiKey, owner_id: UUID | None) -> bool:
    """
    The access rule for jobs and runs: their owner, or the
    administrator.

    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param owner_id: The owning key's id.
    :type owner_id: UUID | None
    :return: True if the caller may see and change it.
    :rtype: bool
    """
    return owner_id == api_key.id or is_admin_key(api_key)


async def get_owned_job(
    job_id: UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Job:
    """
    Load a job the caller may act on (``may_act_on``).

    :param job_id: Job id from the URL path.
    :type job_id: UUID
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The job.
    :rtype: Job
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    job = await db.get(Job, job_id)
    if job is None or not may_act_on(api_key, job.api_key_id):
        raise not_found("Job", job_id)
    return job


async def get_owned_run(
    run_id: UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Run:
    """
    Load a run the caller may act on (``may_act_on``).

    :param run_id: Run id from the URL path.
    :type run_id: UUID
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The run.
    :rtype: Run
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    run = await db.get(Run, run_id)
    if run is None or not may_act_on(api_key, run.owner_id):
        raise not_found("Run", run_id)
    return run


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
