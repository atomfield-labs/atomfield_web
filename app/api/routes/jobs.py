"""
HTTP route handlers for simulation jobs and DAG pipelines.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_api_key,
    get_current_catalog,
    get_job_queue,
    get_optional_api_key,
    get_owned_job,
    get_store,
)
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import CurrentCatalog
from app.schemas.job import (
    JobListResponse,
    JobResponse,
    JobSubmitRequest,
    PipelineSubmitRequest,
    PipelineSubmitResponse,
)
from app.services import job_service
from app.services.submission_validation import (
    validate_job_request,
    validate_pipeline_request,
)
from app.storage.store import ArtifactStore

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# -----------------------------------------------------------------------
# Job submission
# -----------------------------------------------------------------------


@router.post("/submit", response_model=JobResponse, status_code=202)
async def submit_job(
    job_req: JobSubmitRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
    current: CurrentCatalog = Depends(get_current_catalog),
):
    """
    Submit a standalone simulation job to the queue.

    :param job_req: Task id and parameters for execution.
    :type job_req: JobSubmitRequest
    :param api_key: Authenticated user API key.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue the job is sent to.
    :type queue: RedisJobQueue
    :param current: The newest release, which the job is checked
        against and pinned to.
    :type current: CurrentCatalog
    :return: Created Job entity with Pending status.
    :rtype: Job
    """
    job_req = validate_job_request(current.catalog, job_req)
    return await job_service.create_job(
        db=db,
        request=job_req,
        queue=queue,
        api_key=api_key,
        release_id=current.release_id,
    )


@router.post(
    "/pipeline/submit",
    response_model=PipelineSubmitResponse,
    status_code=202,
)
async def submit_pipeline(
    pipeline_req: PipelineSubmitRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
    store: ArtifactStore = Depends(get_store),
    current: CurrentCatalog = Depends(get_current_catalog),
):
    """
    Submit a DAG pipeline of simulation jobs.

    :param pipeline_req: Graph nodes, edges, and attached input files.
    :type pipeline_req: PipelineSubmitRequest
    :param api_key: Authenticated user API key.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue the root jobs are sent to.
    :type queue: RedisJobQueue
    :param store: Where attached files are kept for agents.
    :type store: ArtifactStore
    :param current: The newest release, which every node is checked
        against and the run is pinned to.
    :type current: CurrentCatalog
    :return: Pipeline submission receipt and job ID mappings.
    :rtype: dict
    """
    pipeline_req = validate_pipeline_request(current.catalog, pipeline_req)
    return await job_service.submit_pipeline(
        db=db,
        request=pipeline_req,
        queue=queue,
        store=store,
        api_key=api_key,
        release_id=current.release_id,
    )


@router.delete("/clear")
async def clear_my_jobs(
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
):
    """
    Delete all of the caller's jobs and files, and nobody else's.

    Wiping the whole system is not an HTTP operation: it needs shell
    access to the server (``python -m app.cli wipe``).

    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :return: Operation confirmation payload.
    :rtype: dict
    """
    return await job_service.clear_user_data(
        db=db, store=store, api_key_id=api_key.id
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
):
    """
    Delete one of the caller's sessions: its runs, jobs and stored
    files.

    :param session_id: Pipeline session identifier.
    :type session_id: str
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :return: Operation confirmation payload.
    :rtype: dict
    """
    return await job_service.delete_session(
        db=db,
        store=store,
        session_id=session_id,
        api_key_id=api_key.id,
    )


# -----------------------------------------------------------------------
# Job queries
# -----------------------------------------------------------------------


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    List jobs with optional status filter and pagination.

    :param status: Optional execution status filter.
    :type status: str | None
    :param limit: Maximum records to return.
    :type limit: int
    :param offset: Number of records to skip.
    :type offset: int
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Paginated list of jobs and total count.
    :rtype: JobListResponse
    """
    if not api_key:
        return JobListResponse(jobs=[], total=0)
    jobs, total = await job_service.list_jobs(
        db=db,
        status=status,
        limit=limit,
        offset=offset,
        api_key_id=api_key.id,
    )
    return JobListResponse(jobs=jobs, total=total)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job: Job = Depends(get_owned_job)):
    """
    Retrieve status and output metadata of one of the caller's jobs.

    :param job: Job the caller owns (any job, for the admin).
    :type job: Job
    :return: Job entity containing execution status and output metrics.
    :rtype: Job
    """
    return job


@router.get("/{job_id}/logs")
async def get_job_logs(
    job: Job = Depends(get_owned_job),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
):
    """
    Fetch live logs and generated artifact file list for a job.

    :param job: Job the caller owns (any job, for the admin).
    :type job: Job
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the job's uploaded files are kept.
    :type store: ArtifactStore
    :return: Dictionary containing logs, status, and artifact listing.
    :rtype: dict
    """
    return await job_service.get_job_logs_and_artifacts(
        db=db, store=store, job_id=job.id
    )
