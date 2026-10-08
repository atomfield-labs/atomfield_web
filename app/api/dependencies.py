"""
app/api/dependencies.py — Shared FastAPI Dependencies

📚 LESSON: Why centralize dependencies?

    A "dependency" in FastAPI is any function injected via `Depends(...)`.
    Right now we only have `get_db`. But soon you'll have:
    • get_current_user (auth)
    • get_redis_pool
    • rate_limiter
    • request_id_tracker

    Centralizing them here means routes just import and declare —
    no scattered utility functions across files.

📚 LESSON: The Redis pool dependency
    Instead of `request.app.state.redis` (coupling routes to app state),
    we expose it as a dependency. This makes testing easier —
    you can override `get_redis` in tests with a mock pool.
"""

from fastapi import Request
from arq import ArqRedis


async def get_redis(request: Request) -> ArqRedis:
    """
    Inject the ARQ Redis pool into route handlers.

    📚 LESSON: This breaks the tight coupling between routes and app.state.
    In tests, you can do:
        app.dependency_overrides[get_redis] = lambda: mock_redis_pool
    """
    return request.app.state.redis
