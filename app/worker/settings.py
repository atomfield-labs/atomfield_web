"""
app/worker/settings.py — ARQ Worker Configuration

📚 LESSON: Convention-over-Configuration (ARQ's approach)

    ARQ expects a class with well-known attribute names:
    • functions      → list of async callables this worker handles
    • redis_settings → where to find the Redis broker
    • max_jobs       → max concurrent tasks (worker concurrency)
    • job_timeout    → auto-kill jobs exceeding this duration
    • keep_result    → how long to cache results in Redis

    No decorators. No YAML config files. Just a plain class.
    ARQ reads the class attributes at startup and configures itself.

    The class is referenced by its import path on the CLI:
        uv run arq app.worker.settings.WorkerConfig
"""

from arq.connections import RedisSettings
from app.core.config import settings
from app.worker.tasks import execute_script


class WorkerConfig:
    """ARQ worker configuration — referenced by CLI as module path."""
    functions = [execute_script]
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
    )
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = settings.WORKER_JOB_TIMEOUT
    keep_result = settings.WORKER_KEEP_RESULT
