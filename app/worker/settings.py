"""
ARQ background worker runtime configuration.
"""

from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import settings
from app.worker.tasks import execute_script


class WorkerConfig:
    """
    Configuration specification consumed by the ARQ background worker.
    """

    functions: ClassVar[list] = [execute_script]
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
    )
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = settings.WORKER_JOB_TIMEOUT
    keep_result = settings.WORKER_KEEP_RESULT
