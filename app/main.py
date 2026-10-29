"""
AtomField application entrypoint and composition root.
Configures FastAPI, lifespan hooks, middleware, and route mounting.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auth import provision_house_target
from app.api.router import api_router
from app.catalog.catalog import Catalog
from app.core.broker import create_redis
from app.core.config import settings
from app.core.security import display_prefix, hash_api_key
from app.db.session import AsyncSessionLocal, engine
from app.events.redis_bus import RedisEventBus
from app.models.api_key import ApiKey
from app.models.user import User
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import ReleaseCatalogs
from app.runs.lifecycle import SilenceLimits
from app.scheduler.sweeper import Sweeper
from app.storage.links import LinkSigner
from app.storage.store import LocalDiskStore

ADMIN_QUOTA = 999999
ADMIN_LABEL = "Cluster Administrator"
# Every API process derives the same administrator id from the same key.
ADMIN_ID_NAMESPACE = uuid.UUID("5b0f8e7e-6d2c-4f4b-9a39-6f2d7e1c3a10")
HEALTHY = "AtomField Core Online"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Set the server up, serve, and release what it holds at shutdown.

    :param app: FastAPI application instance.
    :type app: FastAPI
    :return: Async generator yielding control to the application context.
    :rtype: AsyncGenerator[None, None]
    """
    await set_up(app)
    sweeper_task = start_sweeper(app) if settings.SWEEPER_ENABLED else None
    try:
        yield
    finally:
        await stop_task(sweeper_task)
        await app.state.redis.aclose()
        await engine.dispose()


async def set_up(app: FastAPI) -> None:
    """
    Prepare what the routes use. The schema is owned by migrations
    (``python -m app.db.migrate``), which run before the server starts.

    The catalog is loaded, and checked, first: a broken catalog must
    stop the server here, not fail someone's submission later.
    Releases bring their own catalogs; this file serves runs without
    one.

    :param app: FastAPI application instance.
    :type app: FastAPI
    """
    unreleased = Catalog.from_path(Path(settings.CATALOG_PATH))
    app.state.catalogs = ReleaseCatalogs(unreleased)
    app.state.store = create_store()
    async with AsyncSessionLocal() as session:
        await provision_admin(session)
        await provision_house_target(session)
    app.state.redis = create_redis()
    app.state.job_queue = RedisJobQueue(app.state.redis)
    app.state.event_bus = RedisEventBus(app.state.redis)


async def stop_task(task: asyncio.Task | None) -> None:
    """
    Cancel a background task, if there is one, and wait for it to end.

    :param task: The task.
    :type task: asyncio.Task | None
    """
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def create_store() -> LocalDiskStore:
    """
    Open the server's file store.

    :return: Store in ``STORAGE_DIR``, signing with
        ``STORAGE_SIGNING_KEY``.
    :rtype: LocalDiskStore
    :raises RuntimeError: If no signing key is configured: links signed
        with a made-up key would break across processes and restarts.
    """
    if not settings.STORAGE_SIGNING_KEY:
        raise RuntimeError("Set STORAGE_SIGNING_KEY (openssl rand -hex 32)")
    signer = LinkSigner(settings.STORAGE_SIGNING_KEY)
    return LocalDiskStore(Path(settings.STORAGE_DIR), signer)


def admin_person(admin_id: uuid.UUID) -> Insert:
    """
    The insert of the administrator as a person, skipped if they exist.

    :param admin_id: Their id, derived from the admin key.
    :type admin_id: uuid.UUID
    :return: The statement.
    :rtype: Insert
    """
    person = insert(User).values(
        id=admin_id, name=ADMIN_LABEL, is_admin=True, quota_limit=ADMIN_QUOTA
    )
    return person.on_conflict_do_nothing(index_elements=[User.id])


def admin_key(admin_id: uuid.UUID, key_hash: str) -> Insert:
    """
    The insert of the administrator's key, skipped if it exists.

    :param admin_id: The administrator's id.
    :type admin_id: uuid.UUID
    :param key_hash: Fingerprint of ``ADMIN_API_KEY``.
    :type key_hash: str
    :return: The statement.
    :rtype: Insert
    """
    key = insert(ApiKey).values(
        user_id=admin_id,
        key_hash=key_hash,
        key_prefix=display_prefix(settings.ADMIN_API_KEY),
        label=ADMIN_LABEL,
    )
    return key.on_conflict_do_nothing(index_elements=[ApiKey.key_hash])


async def create_admin(session: AsyncSession, key_hash: str) -> None:
    """
    Create the administrator and their key. Neither insert can clash:
    every process derives the same id from the key, and rows that
    already exist are skipped, so processes starting together are fine.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param key_hash: Fingerprint of ``ADMIN_API_KEY``.
    :type key_hash: str
    """
    admin_id = uuid.uuid5(ADMIN_ID_NAMESPACE, key_hash)
    await session.execute(admin_person(admin_id))
    await session.execute(admin_key(admin_id, key_hash))


async def provision_admin(session: AsyncSession) -> None:
    """
    Make sure the administrator from ``ADMIN_API_KEY`` exists: a person
    marked admin who owns that key. A key from before people existed
    keeps its person, who is made admin.

    :param session: Open database session; committed here.
    :type session: AsyncSession
    """
    if not settings.ADMIN_API_KEY:
        return
    key_hash = hash_api_key(settings.ADMIN_API_KEY)
    known = exists().where(ApiKey.key_hash == key_hash)
    if not await session.scalar(select(known)):
        await create_admin(session, key_hash)
    owner = select(ApiKey.user_id).where(ApiKey.key_hash == key_hash)
    promote = update(User).where(User.id == owner.scalar_subquery())
    await session.execute(promote.values(is_admin=True))
    await session.commit()


def silence_limits() -> SilenceLimits:
    """
    How long a job's agent may stay silent before the job counts as
    lost, by kind of job, from the settings.

    :return: The limits.
    :rtype: SilenceLimits
    """
    scheduled = settings.SCHEDULED_LEASE_TIMEOUT_SECONDS
    return SilenceLimits(
        local=timedelta(seconds=settings.LEASE_TIMEOUT_SECONDS),
        scheduled=timedelta(seconds=scheduled),
    )


def start_sweeper(app: FastAPI) -> asyncio.Task:
    """
    Start the sweeper loop in the background of this API process.

    :param app: Application whose Redis client and queue it uses.
    :type app: FastAPI
    :return: The running loop's task, cancelled at shutdown.
    :rtype: asyncio.Task
    """
    sweeper = Sweeper(
        AsyncSessionLocal,
        app.state.job_queue,
        app.state.event_bus,
        app.state.redis,
        app.state.store,
        interval_seconds=settings.SWEEP_INTERVAL_SECONDS,
        limits=silence_limits(),
        deadline_grace=timedelta(seconds=settings.DEADLINE_GRACE_SECONDS),
    )
    return asyncio.create_task(sweeper.run_forever())


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Distributed job scheduler and DAG execution engine for "
        "computational chemistry."
    ),
    lifespan=lifespan,
)

# Keys travel in a header, never in cookies, so no origin needs the
# browser's credentials mode: with it, "*" would admit every site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard API Gateway
app.include_router(api_router)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """
    Service liveness probe returning system identity and runtime status.

    :return: Dictionary containing service status, version, and environment.
    :rtype: dict[str, str]
    """
    return {
        "status": HEALTHY,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }
