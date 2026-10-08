"""
AtomField — Application Entrypoint (Enterprise Architecture)

📚 LESSON: The Composition Root

    In a DDD/layered architecture, main.py is the "Composition Root" —
    the one place where you WIRE everything together:
    • Create the FastAPI app
    • Attach the lifespan (startup/shutdown hooks)
    • Include the routers (modular route sets)
    • Register middleware (CORS, logging, etc.)

    It imports FROM every layer but no layer imports FROM it.
    This prevents circular dependencies and keeps the dependency
    graph as a clean tree (not a web).

Architecture:

    app/main.py   (this file — composition root)
        ├── app/core/config.py          (settings singleton)
        ├── app/db/base.py              (ORM base registry)
        ├── app/db/session.py           (engine + session factory)
        ├── app/models/job.py           (Job ORM entity)
        ├── app/schemas/job.py          (Pydantic I/O contracts)
        ├── app/services/job_service.py (business logic)
        ├── app/api/routes/jobs.py      (HTTP controllers)
        ├── app/api/dependencies.py     (DI utilities)
        └── app/worker/
            ├── tasks.py                (ARQ background tasks)
            └── settings.py             (ARQ worker config)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.db.session import engine
from app.db.base import Base

# 📚 LESSON: This import has a side effect — it registers the Job model
# with Base.metadata. Without it, create_all() would create zero tables.
# This is a common "gotcha" with SQLAlchemy: unused imports that are critical.
from app.models.job import Job  # noqa: F401 — registers the model

from app.api.routes import jobs as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    📚 LESSON: Lifespan vs @app.on_event
        @app.on_event("startup") is deprecated in FastAPI ≥ 0.93.
        The lifespan pattern is the modern replacement:
        • Startup code BEFORE yield
        • Shutdown code AFTER yield
        • The app serves requests BETWEEN them
        • Resources can be shared via app.state
    """
    # === STARTUP ===

    # Create database tables (Phase 1-3 convenience)
    # 📚 In production Phase 4+, replace with Alembic migrations:
    #   alembic upgrade head
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Redis connection pool for the message broker
    app.state.redis = await create_pool(
        RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    )

    yield  # ← Application serves requests here

    # === SHUTDOWN ===
    app.state.redis.close()
    await app.state.redis.wait_closed()


# -----------------------------------------------------------------------
# Application Factory
# -----------------------------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A distributed job scheduler & DAG executor for materials science simulations.",
    lifespan=lifespan,
)

# -----------------------------------------------------------------------
# 📚 LESSON: CORS Middleware (Cross-Origin Resource Sharing)
#   When the React frontend (Phase 5, e.g. localhost:3000) calls
#   the API (localhost:8000), the browser blocks it by default —
#   this is the Same-Origin Policy.
#   CORS middleware tells the browser: "requests from these origins are OK".
#   In production, replace "*" with your actual domain(s).
# -----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------
# Register Routers
# -----------------------------------------------------------------------
app.include_router(jobs_router.router)


# -----------------------------------------------------------------------
# System Endpoints (not in a router — they're app-level)
# -----------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health_check():
    """
    Liveness probe for load balancers and monitoring.

    📚 LESSON: Health checks in production
        Kubernetes readinessProbe / livenessProbe hit this endpoint.
        • 200 → container is healthy, send it traffic
        • 503 → container is sick, restart it
        A more advanced version would also ping Redis and PostgreSQL
        to verify dependencies are reachable (a "deep health check").
    """
    return {
        "status": "AtomField Enterprise Core Online",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }