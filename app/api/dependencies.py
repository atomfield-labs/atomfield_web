"""
Shared FastAPI route dependencies for database, cache, and authentication.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evidence import EvidenceCollector
from app.ai.pages import PageLibrary
from app.ai.reviews import ReviewRunner
from app.ai.vault import KeyVault
from app.ai.vendors import AiVendor, LlmClient, client_for
from app.api.errors import (
    forbidden,
    not_found,
    unauthorized,
)
from app.core.config import settings
from app.core.rate_limit import FixedWindowRateLimiter, RateLimit
from app.core.security import API_KEY_HEADER, SESSION_COOKIE, hash_api_key
from app.db.session import AsyncSessionLocal, get_db
from app.events.bus import EventBus
from app.labs.access import allowed_workflows
from app.models.api_key import ApiKey
from app.models.browser_session import BrowserSession
from app.models.job import Job
from app.models.lab import Lab
from app.models.run import Run
from app.models.user import Role, User
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import CurrentCatalog, ReleaseCatalogs
from app.sign_in.flow import SignInFlow
from app.storage.store import LocalDiskStore

# Makes a vendor's client from a person's key.
LlmFactory = Callable[[AiVendor, str], LlmClient]
AI_CALL_LIMIT = "ai-call"
CLOUDFLARE_CLIENT_HEADER = "CF-Connecting-IP"
UNKNOWN_CLIENT = "unknown"
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
SIGN_IN_LIMIT = "sign-in"
PAIRING_START_LIMIT = "pairing-start"
CODE_LOOKUP_LIMIT = "pairing-code"
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
NOT_OWNER_MESSAGE = "Only the platform's owner may do this."
BROWSER_ONLY_MESSAGE = "This is done in the web app, signed in."
LAB_KIND = "Lab"


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


async def get_browser_user(caller: Caller = Depends(get_caller)) -> User:
    """
    The person, signed in on a browser. Keys are managed only there,
    behind the institute sign-in, so a leaked key cannot make itself
    new keys.

    :param caller: Who is calling.
    :type caller: Caller
    :return: The person.
    :rtype: User
    :raises HTTPException: 403 for a caller using a key.
    """
    if caller.api_key is not None:
        raise forbidden(BROWSER_ONLY_MESSAGE)
    return caller.user


async def require_owner(user: User = Depends(get_current_user)) -> User:
    """
    Let only the platform's owner through. A lab's admin is not one.

    :param user: The person making the request.
    :type user: User
    :return: The owner.
    :rtype: User
    :raises HTTPException: 403 for anyone else.
    """
    if not user.is_owner:
        raise forbidden(NOT_OWNER_MESSAGE)
    return user


async def require_browser_owner(
    user: User = Depends(get_browser_user),
) -> User:
    """
    Let only the platform's owner through, signed in on a browser.

    :param user: The person, signed in.
    :type user: User
    :return: The owner.
    :rtype: User
    :raises HTTPException: 403 for anyone else.
    """
    if not user.is_owner:
        raise forbidden(NOT_OWNER_MESSAGE)
    return user


async def get_managed_lab(
    lab_id: UUID,
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> Lab:
    """
    A lab the caller runs: any for the owner, their own for its admin.

    :param lab_id: Lab id from the URL path.
    :type lab_id: UUID
    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The lab.
    :rtype: Lab
    :raises HTTPException: 404 if missing or someone else's.
    """
    lab = await db.get(Lab, lab_id)
    its_admin = user.role == Role.ADMIN and user.lab_id == lab_id
    if lab is None or not (user.is_owner or its_admin):
        raise not_found(LAB_KIND, lab_id)
    return lab


async def get_my_catalog(
    user: User = Depends(get_current_user),
    current: CurrentCatalog = Depends(get_current_catalog),
    db: AsyncSession = Depends(get_db),
) -> CurrentCatalog:
    """
    The catalog as this person sees it: the one gate behind the task
    menu, the templates and every submission. What is outside their
    workflows is not there for them; an owner sees everything.

    :param user: The person making the request.
    :type user: User
    :param current: The current release and its whole catalog.
    :type current: CurrentCatalog
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The release, and the catalog limited to this person.
    :rtype: CurrentCatalog
    """
    if user.is_owner:
        return current
    allowed = await allowed_workflows(db, user)
    return replace(current, catalog=current.catalog.limited_to(allowed))


def may_act_on(user: User, owner_id: UUID | None) -> bool:
    """
    The access rule for jobs and runs: whoever submitted them, or the
    platform's owner.

    :param user: The person making the request.
    :type user: User
    :param owner_id: The owner's id.
    :type owner_id: UUID | None
    :return: True if the person may see and change it.
    :rtype: bool
    """
    return owner_id == user.id or user.is_owner


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


@dataclass(frozen=True, slots=True)
class AddressLimit:
    """
    A dependency telling whether this request's address is still within
    a per-minute limit. The limit is read at each request, so tests can
    lower it.

    :param name: What is limited, part of the counter's key.
    :type name: str
    :param per_minute: Reads the limit from the settings.
    :type per_minute: Callable[[], int]
    """

    name: str
    per_minute: Callable[[], int]

    async def __call__(
        self, request: Request, redis: Redis = Depends(get_redis)
    ) -> bool:
        """
        Count this request, and say whether it is within the limit.

        :param request: Incoming request.
        :type request: Request
        :param redis: Shared Redis client holding the counters.
        :type redis: Redis
        :return: True while within the limit.
        :rtype: bool
        """
        limit = RateLimit(
            name=self.name,
            max_requests=self.per_minute(),
            window_seconds=SECONDS_PER_MINUTE,
        )
        limiter = FixedWindowRateLimiter(redis, limit)
        decision = await limiter.check(client_address(request))
        return decision.allowed


async def get_key_vault(request: Request) -> KeyVault | None:
    """
    Provide the vault that keeps people's AI keys.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: The vault; None if this server has no secret for it.
    :rtype: KeyVault | None
    """
    return request.app.state.key_vault


async def get_llm_factory() -> LlmFactory:
    """
    Provide what makes a vendor's client; tests replace it with a fake.

    :return: The factory.
    :rtype: LlmFactory
    """
    return client_for


async def get_review_runner(
    request: Request,
    vault: KeyVault | None = Depends(get_key_vault),
    make_client: LlmFactory = Depends(get_llm_factory),
) -> ReviewRunner | None:
    """
    Provide what runs an AI review.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :param vault: The vault; None if this server has no secret for it.
    :type vault: KeyVault | None
    :param make_client: Makes a vendor's client.
    :type make_client: LlmFactory
    :return: The runner; None without a vault, as no key can be read.
    :rtype: ReviewRunner | None
    """
    if vault is None:
        return None
    state = request.app.state
    library = PageLibrary(state.store, state.http)
    collector = EvidenceCollector(state.store, library)
    return ReviewRunner(
        AsyncSessionLocal,
        state.catalogs,
        collector,
        state.store,
        vault,
        make_client,
    )


async def ai_call_allowed(
    user: User = Depends(get_browser_user),
    redis: Redis = Depends(get_redis),
) -> bool:
    """
    Count a call to an AI vendor against the person's limit per minute.

    :param user: The person, signed in.
    :type user: User
    :param redis: Shared Redis client holding the counters.
    :type redis: Redis
    :return: True while within the limit.
    :rtype: bool
    """
    limit = RateLimit(
        name=AI_CALL_LIMIT,
        max_requests=settings.AI_CALLS_PER_MINUTE,
        window_seconds=SECONDS_PER_MINUTE,
    )
    decision = await FixedWindowRateLimiter(redis, limit).check(str(user.id))
    return decision.allowed


# Each one started keeps its secrets in Redis for minutes, so a flood
# of starts is turned back.
sign_in_allowed = AddressLimit(
    SIGN_IN_LIMIT, lambda: settings.SIGN_IN_LIMIT_PER_MINUTE
)
pairing_start_allowed = AddressLimit(
    PAIRING_START_LIMIT, lambda: settings.PAIRING_LIMIT_PER_MINUTE
)
# Codes are short; few guesses a minute keep them unguessable.
code_lookup_allowed = AddressLimit(
    CODE_LOOKUP_LIMIT, lambda: settings.PAIRING_LIMIT_PER_MINUTE
)
