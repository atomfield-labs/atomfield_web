"""
ARQ entry point: run one queued job and record its outcome.

How a task runs is decided by its catalog definition
(``app.worker.execution``); this module only moves the job through its
states and starts dependent jobs.
"""

import asyncio
import traceback
from pathlib import Path
from typing import Any

from app.catalog.catalog import Catalog
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.job_service import (
    evaluate_downstream_dependencies,
    mark_job_failed,
    mark_job_running,
    mark_job_success,
)
from app.worker.execution import run_catalog_task

CATALOG_KEY = "catalog"


async def load_catalog(worker_context: dict[str, Any]) -> None:
    """
    Load the task catalog once per worker process, at startup.

    A broken catalog stops the worker here instead of failing jobs.

    :param worker_context: ARQ's per-worker context dictionary.
    :type worker_context: dict[str, Any]
    """
    catalog_path = Path(settings.CATALOG_PATH)
    worker_context[CATALOG_KEY] = Catalog.from_path(catalog_path)


async def _mark_job_running_in_session(job_id: str) -> None:
    """
    Update database record marking the given job status to Running.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_running(job_id, session)


async def _handle_execution_success(
    job_id: str,
    output: Any,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> None:
    """
    Record job success and propagate DAG resolution to downstream jobs.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :param output: JSON output dictionary or simulation results.
    :type output: Any
    :param redis_client: Redis connection client for ARQ queueing.
    :type redis_client: Any
    :param duration_seconds: Elapsed simulation execution time.
    :type duration_seconds: float | None
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_success(
            job_id, output, session, duration_seconds=duration_seconds
        )
        await evaluate_downstream_dependencies(session, job_id, redis_client)


async def _handle_execution_failure(
    job_id: str,
    error_message: str,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> None:
    """
    Record job failure and propagate failure status to downstream dependencies.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :param error_message: Reason or stack trace of the failure.
    :type error_message: str
    :param redis_client: Redis connection client for ARQ queueing.
    :type redis_client: Any
    :param duration_seconds: Elapsed execution duration before failure.
    :type duration_seconds: float | None
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_failed(
            job_id, error_message, session, duration_seconds=duration_seconds
        )
        await evaluate_downstream_dependencies(session, job_id, redis_client)


def _format_worker_exception(error_exc: Exception) -> str:
    """
    Format exception name and full traceback into string for error reporting.

    :param error_exc: Caught Python exception instance.
    :type error_exc: Exception
    :return: Formatted error trace string.
    :rtype: str
    """
    return f"{type(error_exc).__name__}: {error_exc}\n{traceback.format_exc()}"


async def _process_task_result(
    result: dict[str, Any],
    job_id: str,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> Any:
    """
    Dispatch success or failure handling based on task execution result.

    :param result: Result mapping returned from run_script_task.
    :type result: dict[str, Any]
    :param job_id: Unique job identifier string.
    :type job_id: str
    :param redis_client: ARQ Redis connection pool.
    :type redis_client: Any
    :param duration_seconds: Elapsed simulation duration in seconds.
    :type duration_seconds: float | None
    :return: Simulation output payload on success.
    :rtype: Any
    :raises RuntimeError: If sandbox execution status is failed.
    """
    if result["status"] == "success":
        await _handle_execution_success(
            job_id, result["output"], redis_client, duration_seconds
        )
        return result["output"]

    error_msg = result["error"]
    await _handle_execution_failure(
        job_id, error_msg, redis_client, duration_seconds
    )
    raise RuntimeError(f"Sandbox execution failed: {error_msg}")


async def execute_script(
    worker_context: dict[str, Any],
    job_id: str,
    script_name: str,
    parameters: dict[str, Any] | None,
    input_files: dict[str, list[str]] | None = None,
) -> Any:
    """
    Core ARQ worker entry point invoked upon dequeuing a job.

    :param worker_context: ARQ context; holds the catalog and Redis.
    :type worker_context: dict[str, Any]
    :param job_id: Target job identifier string.
    :type job_id: str
    :param script_name: Id of the catalog task to run.
    :type script_name: str
    :param parameters: Stored job parameters.
    :type parameters: dict[str, Any] | None
    :param input_files: Input port name -> uploaded file names. None
        for jobs queued before this argument existed.
    :type input_files: dict[str, list[str]] | None
    :return: Completed simulation output payload.
    :rtype: Any
    """
    catalog: Catalog = worker_context[CATALOG_KEY]
    redis_client = worker_context.get("redis")
    await _mark_job_running_in_session(job_id)

    event_loop = asyncio.get_event_loop()
    start_time = event_loop.time()
    try:
        task = catalog.get(script_name)
        result = await asyncio.to_thread(
            run_catalog_task,
            task,
            parameters or {},
            input_files or {},
            job_id,
        )
        duration = round(event_loop.time() - start_time, 2)
        return await _process_task_result(
            result, job_id, redis_client, duration
        )
    except Exception as worker_exc:
        duration = round(event_loop.time() - start_time, 2)
        if not isinstance(worker_exc, RuntimeError):
            error_text = _format_worker_exception(worker_exc)
            await _handle_execution_failure(
                job_id, error_text, redis_client, duration
            )
        raise
