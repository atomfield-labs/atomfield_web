"""
ARQ background worker runtime configuration.
"""

from typing import ClassVar

from app.core.broker import build_redis_settings
from app.core.config import settings
from app.worker.tasks import execute_script, load_catalog


class WorkerConfig:
    """
    Configuration specification consumed by the ARQ background worker.
    """

    functions: ClassVar[list] = [execute_script]
    on_startup = load_catalog
    redis_settings = build_redis_settings()
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = settings.WORKER_JOB_TIMEOUT
    keep_result = settings.WORKER_KEEP_RESULT
