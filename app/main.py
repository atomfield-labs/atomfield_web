"""
AtomField application entrypoint and composition root.
Configures FastAPI, lifespan hooks, middleware, and route mounting.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import settings
from app.core.security import hash_api_key
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.api_key import ApiKey


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup lifecycle and graceful shutdown resources.

    :param app: FastAPI application instance.
    :type app: FastAPI
    :return: Async generator yielding control to the application context.
    :rtype: AsyncGenerator[None, None]
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

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

    app.state.redis = await create_pool(
        RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    )
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()


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
