"""
app/db/session.py — Async Engine & Session Factory

📚 LESSON: Engine vs Session vs Connection

    Engine   = the "factory" that manages a CONNECTION POOL to PostgreSQL.
              Think of it as a database client singleton. Created once at startup.

    Session  = a unit-of-work container. It batches your ORM operations (add, update,
              delete) and flushes them to the database in a single transaction on commit().
              Short-lived — one per HTTP request.

    Connection = the raw TCP link to PostgreSQL. Sessions borrow a connection from the
                engine's pool, use it, then return it. You rarely touch connections directly.

    The pool prevents "connection storms" — if 1000 requests hit at once, the pool
    limits to ~10 concurrent TCP connections (configurable via pool_size), queuing the rest.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # 📚 LESSON: Pool tuning for production
    # pool_size=5 → max steady-state connections (default 5)
    # max_overflow=10 → burst capacity above pool_size (default 10)
    # pool_pre_ping=True → test connections before using them (handles DB restarts)
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency Injector.

    📚 LESSON: The yield-based dependency pattern
        FastAPI calls this function for each request, gets a session via `yield`,
        injects it into the route handler, and after the response is sent,
        resumes past the yield to close the session.

        This guarantees cleanup even if the route raises an exception.
        It's equivalent to a try/finally block, but declarative.
    """
    async with AsyncSessionLocal() as session:
        yield session
