"""
AtomField application entrypoint and composition root.
Configures FastAPI, lifespan hooks, middleware, and route mounting.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.agents.auth import provision_house_target
from app.api.router import api_router
from app.catalog.catalog import Catalog
from app.core.broker import create_redis
from app.core.config import settings
from app.core.security import hash_api_key
from app.db.session import AsyncSessionLocal, engine
from app.models.api_key import ApiKey
from app.queue.job_queue import RedisJobQueue
from app.scheduler.sweeper import Sweeper


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup lifecycle and graceful shutdown resources.

    :param app: FastAPI application instance.
    :type app: FastAPI
    :return: Async generator yielding control to the application context.
    :rtype: AsyncGenerator[None, None]
    """
    # The schema is owned by migrations (python -m app.db.migrate),
    # which run before the server starts.

    # Load (and validate) the catalog first: a broken catalog must stop
    # the server here, not fail someone's submission later.
    app.state.catalog = Catalog.from_path(Path(settings.CATALOG_PATH))

    # Auto-provision cluster administrator key if configured
    if settings.ADMIN_API_KEY:
        admin_hash = hash_api_key(settings.ADMIN_API_KEY)
        async with AsyncSessionLocal() as session:
            stmt = select(ApiKey).where(ApiKey.key_hash == admin_hash)
            res = await session.execute(stmt)
            if not res.scalars().first():
                prefix = settings.ADMIN_API_KEY[:8] + "..."
                admin_key = ApiKey(
                    key_hash=admin_hash,
                    key_prefix=prefix,
                    label="Cluster Administrator",
                    quota_limit=999999,
                    quota_used=0,
                    is_active=True,
                )
                session.add(admin_key)
                await session.commit()

    app.state.redis = create_redis()
    app.state.job_queue = RedisJobQueue(app.state.redis)
    async with AsyncSessionLocal() as session:
        await provision_house_target(session)
    sweeper_task = start_sweeper(app) if settings.SWEEPER_ENABLED else None
    try:
        yield
    finally:
        if sweeper_task is not None:
            sweeper_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper_task
        await app.state.redis.aclose()
        await engine.dispose()


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
        app.state.redis,
        interval_seconds=settings.SWEEP_INTERVAL_SECONDS,
        lease_timeout=timedelta(seconds=settings.LEASE_TIMEOUT_SECONDS),
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
        "status": "AtomField Core Online",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }
