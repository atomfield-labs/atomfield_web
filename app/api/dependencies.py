"""
Shared FastAPI route dependencies for database, cache, and authentication.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    forbidden,
    not_found,
    too_many_requests,
    unauthorized,
)
from app.core.config import settings
from app.core.rate_limit import FixedWindowRateLimiter, RateLimit
from app.core.security import API_KEY_HEADER, SESSION_COOKIE, hash_api_key
from app.db.session import get_db
from app.events.bus import EventBus
from app.models.api_key import ApiKey
from app.models.browser_session import BrowserSession
from app.models.job import Job
from app.models.run import Run
from app.models.user import User
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import CurrentCatalog, ReleaseCatalogs
from app.sign_in.flow import SignInFlow
from app.storage.store import LocalDiskStore

CLOUDFLARE_CLIENT_HEADER = "CF-Connecting-IP"
UNKNOWN_CLIENT = "unknown"
SECONDS_PER_HOUR = 3600
ORIGIN_HEADER = "Origin"
# Requests that only read, which a browser may make from any page.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


NOT_SIGNED_IN_MESSAGE = (
    f"Sign in, or send an API key in the '{API_KEY_HEADER}' header."
)
INVALID_KEY_MESSAGE = "Invalid or deactivated API key."
SESSION_ENDED_MESSAGE = "Your sign-in has ended. Please sign in again."
CROSS_SITE_MESSAGE = (
    "A signed-in browser may change things only from AtomField's pages."
)
NOT_ADMIN_MESSAGE = "Administrator privileges required."
TOO_MANY_KEYS_MESSAGE = "Too many new API keys from this address. Try later."


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


async def get_sign_in(request: Request) -> SignInFlow | None:
    """
    Provide the sign-in flow made at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: The flow, or None if sign-in is not set up.
    :rtype: SignInFlow | None
    """
    return request.app.state.sign_in


@dataclass(frozen=True, slots=True)
class Caller:
    """
    Who is calling: the person, and the API key their script used (a
    signed-in browser uses none).

    :param user: The person.
    :type user: User
    :param api_key: The key in the request, if any.
    :type api_key: ApiKey | None
    """

    user: User
    api_key: ApiKey | None = None

    @property
    def key_prefix(self) -> str | None:
        """
        The start of the key in use, to tell keys apart.

        :return: The prefix, or None for a browser.
        :rtype: str | None
        """
        return self.api_key.key_prefix if self.api_key else None


async def caller_with_key(db: AsyncSession, secret: str) -> Caller | None:
    """
    The active key with this secret, and its active owner (keys are
    stored as hashes).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param secret: The key as the client sent it.
    :type secret: str
    :return: Key and person, or None if either is unknown or
        deactivated.
    :rtype: Caller | None
    """
    query = (
        select(ApiKey, User)
        .join(User, User.id == ApiKey.user_id)
        .where(
            ApiKey.key_hash == hash_api_key(secret),
            ApiKey.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    found = (await db.execute(query)).first()
    return Caller(user=found.User, api_key=found.ApiKey) if found else None


async def caller_from_browser(db: AsyncSession, token: str) -> Caller | None:
    """
    The active person signed in on the browser holding this session
    secret, while the session lasts.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param token: The secret from the session cookie.
    :type token: str
    :return: The caller, or None.
    :rtype: Caller | None
    """
    query = (
        select(User)
        .join(BrowserSession, BrowserSession.user_id == User.id)
        .where(
            BrowserSession.token_hash == hash_api_key(token),
            BrowserSession.expires_at > func.now(),
            User.is_active.is_(True),
        )
    )
    user = await db.scalar(query)
    return Caller(user=user) if user else None


def check_origin(request: Request) -> None:
    """
    Let a signed-in browser change things only from AtomField's own
    pages. SameSite keeps the session cookie off requests from other
    sites' pages, but every page on the institute's domain counts as
    the same site. The Origin header, which the browser sets and a
    page cannot, says which page asked.

    :param request: Incoming request.
    :type request: Request
    :raises HTTPException: 403 for a change asked from anywhere else.
    """
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get(ORIGIN_HEADER)
    if origin is None or origin != settings.public_origin:
        raise forbidden(CROSS_SITE_MESSAGE)


async def mark_used(db: AsyncSession, caller: Caller) -> None:
    """
    Record when a person, and the key they used if any, were last seen.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param caller: Who called.
    :type caller: Caller
    """
    if caller.api_key is not None:
        used = update(ApiKey).where(ApiKey.id == caller.api_key.id)
        await db.execute(used.values(last_used_at=func.now()))
    seen = update(User).where(User.id == caller.user.id)
    await db.execute(seen.values(last_seen_at=func.now()))
    await db.commit()


async def get_optional_caller(
    request: Request,
    x_api_key: str | None = Header(None, alias=API_KEY_HEADER),
    session_token: str | None = Cookie(None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> Caller | None:
    """
    Who is calling, if they sent a key that works or their browser is
    signed in. Scripts send keys and browsers cookies; a key wins.

    :param request: Incoming request.
    :type request: Request
    :param x_api_key: The key from the request header, if any.
    :type x_api_key: str | None
    :param session_token: The secret from the session cookie, if any.
    :type session_token: str | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The caller, or None.
    :rtype: Caller | None
    :raises HTTPException: 403 if a signed-in browser is asked to
        change something from another site's page.
    """
    if x_api_key:
        caller = await caller_with_key(db, x_api_key)
    elif session_token:
        check_origin(request)
        caller = await caller_from_browser(db, session_token)
    else:
        caller = None
    if caller is not None:
        await mark_used(db, caller)
    return caller


async def get_caller(
    x_api_key: str | None = Header(None, alias=API_KEY_HEADER),
    session_token: str | None = Cookie(None, alias=SESSION_COOKIE),
    caller: Caller | None = Depends(get_optional_caller),
) -> Caller:
    """
    Who is calling; the request is refused unless a key works or the
    browser is signed in.

    :param x_api_key: The key from the request header, if any.
    :type x_api_key: str | None
    :param session_token: The secret from the session cookie, if any.
    :type session_token: str | None
    :param caller: The caller they identify, if any.
    :type caller: Caller | None
    :return: The caller.
    :rtype: Caller
    :raises HTTPException: 401 with nothing to go on, a key that does
        not work, or a sign-in that has ended.
    """
    if caller is not None:
        return caller
    if x_api_key:
        raise unauthorized(INVALID_KEY_MESSAGE)
    if session_token:
        raise unauthorized(SESSION_ENDED_MESSAGE)
    raise unauthorized(NOT_SIGNED_IN_MESSAGE)


async def get_current_user(caller: Caller = Depends(get_caller)) -> User:
    """
    The person making the request.

    :param caller: Who is calling.
    :type caller: Caller
    :return: The person.
    :rtype: User
    """
    return caller.user


async def get_optional_user(
    caller: Caller | None = Depends(get_optional_caller),
) -> User | None:
    """
    The person making the request, if they sent a working key.

    :param caller: Who is calling, if known.
    :type caller: Caller | None
    :return: The person, or None.
    :rtype: User | None
    """
    return caller.user if caller else None


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Let only the administrator through.

    :param user: The person making the request.
    :type user: User
    :return: The administrator.
    :rtype: User
    :raises HTTPException: 403 for anyone else.
    """
    if not user.is_admin:
        raise forbidden(NOT_ADMIN_MESSAGE)
    return user


def may_act_on(user: User, owner_id: UUID | None) -> bool:
    """
    The access rule for jobs and runs: their owner, or the
    administrator.

    :param user: The person making the request.
    :type user: User
    :param owner_id: The owner's id.
    :type owner_id: UUID | None
    :return: True if the person may see and change it.
    :rtype: bool
    """
    return owner_id == user.id or user.is_admin


async def get_owned_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    """
    Load a job the caller may act on (``may_act_on``).

    :param job_id: Job id from the URL path.
    :type job_id: UUID
    :param user: The person making the request.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The job.
    :rtype: Job
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    job = await db.get(Job, job_id)
    if job is None or not may_act_on(user, job.owner_id):
        raise not_found("Job", job_id)
    return job


async def get_owned_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    """
    Load a run the caller may act on (``may_act_on``).

    :param run_id: Run id from the URL path.
    :type run_id: UUID
    :param user: The person making the request.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The run.
    :rtype: Run
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    run = await db.get(Run, run_id)
    if run is None or not may_act_on(user, run.owner_id):
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
        raise too_many_requests(
            TOO_MANY_KEYS_MESSAGE, decision.retry_after_seconds
        )
