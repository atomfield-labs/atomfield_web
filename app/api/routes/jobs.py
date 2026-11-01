"""
HTTP route handlers for simulation jobs and DAG pipelines.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_user,
    get_job_queue,
    get_my_catalog,
    get_optional_user,
    get_owned_job,
    get_store,
)
from app.api.errors import not_found
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import CurrentCatalog
from app.runs.states import JobStatus
from app.schemas.job import (
    JobFilesResponse,
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
FILE_KIND = "File"
# A job wrote this file: a browser must never treat it as a page.
NEVER_A_PAGE = {"X-Content-Type-Options": "nosniff"}
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# -----------------------------------------------------------------------
# Job submission
# -----------------------------------------------------------------------


@router.post("/submit", response_model=JobResponse, status_code=202)
async def submit_job(
    job_req: JobSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
    current: CurrentCatalog = Depends(get_my_catalog),
):
    """
    Submit a standalone simulation job to the queue.

    :param job_req: Task id and parameters for execution.
    :type job_req: JobSubmitRequest
    :param user: The person submitting.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue the job is sent to.
    :type queue: RedisJobQueue
    :param current: The newest release as the caller sees it, which the
        job is checked against and pinned to.
    :type current: CurrentCatalog
    :return: Created Job entity with Pending status.
    :rtype: Job
    """
    job_req = validate_job_request(current.catalog, job_req)
    return await job_service.create_job(
        db=db,
        request=job_req,
        queue=queue,
        user=user,
        release_id=current.release_id,
    )


@router.post(
    "/pipeline/submit",
    response_model=PipelineSubmitResponse,
    status_code=202,
)
async def submit_pipeline(
    pipeline_req: PipelineSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
    store: ArtifactStore = Depends(get_store),
    current: CurrentCatalog = Depends(get_my_catalog),
):
    """
    Submit a DAG pipeline of simulation jobs.

    :param pipeline_req: Graph nodes, edges, and attached input files.
    :type pipeline_req: PipelineSubmitRequest
    :param user: The person submitting.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue the root jobs are sent to.
    :type queue: RedisJobQueue
    :param store: Where attached files are kept for agents.
    :type store: ArtifactStore
    :param current: The newest release as the caller sees it, which
        every node is checked against and the run is pinned to.
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
        user=user,
        release_id=current.release_id,
    )


@router.delete("/clear")
async def clear_my_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
):
    """
    Delete all of the caller's jobs and files, and nobody else's.

    Wiping the whole system is not an HTTP operation: it needs shell
    access to the server (``python -m app.cli wipe``).

    :param user: The person asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :return: Operation confirmation payload.
    :rtype: dict
    """
    return await job_service.clear_user_data(
        db=db, store=store, user_id=user.id
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
):
    """
    Delete one of the caller's sessions: its runs, jobs and stored
    files.

    :param session_id: Pipeline session identifier.
    :type session_id: str
    :param user: The person asking.
    :type user: User
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
        user_id=user.id,
    )


# -----------------------------------------------------------------------
# Job queries
# -----------------------------------------------------------------------


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatus | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List the caller's jobs, newest first, a page at a time.

    :param status: Only jobs in this state, if given.
    :type status: JobStatus | None
    :param limit: Most jobs to return (1 to ``MAX_PAGE_SIZE``).
    :type limit: int
    :param offset: Jobs to skip.
    :type offset: int
    :param user: The person asking, if known.
    :type user: User | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Paginated list of jobs and total count.
    :rtype: JobListResponse
    """
    if not user:
        return JobListResponse(jobs=[], total=0)
    jobs, total = await job_service.list_jobs(
        db, user.id, status=status, limit=limit, offset=offset
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
    store: ArtifactStore = Depends(get_store),
):
    """
    The end of a job's log and the list of its files.

    :param job: Job the caller owns (any job, for the admin).
    :type job: Job
    :param store: Where the job's uploaded files are kept.
    :type store: ArtifactStore
    :return: Status, log tail, file names and outputs.
    :rtype: dict
    """
    return await job_service.job_logs_and_files(store, job)


@router.get("/{job_id}/files", response_model=JobFilesResponse)
async def list_job_files(
    job: Job = Depends(get_owned_job),
) -> JobFilesResponse:
    """
    The files of a job that can be read here.

    :param job: Job the caller owns (any job, for the admin).
    :type job: Job
    :return: Those files, and how many others stay behind.
    :rtype: JobFilesResponse
    """
    return job_service.job_files(job)


@router.get("/{job_id}/files/{name}", response_class=PlainTextResponse)
async def get_job_file(
    name: str,
    job: Job = Depends(get_owned_job),
    store: ArtifactStore = Depends(get_store),
) -> PlainTextResponse:
    """
    One of a job's uploaded files, always as plain text.

    :param name: The file.
    :type name: str
    :param job: Job the caller owns (any job, for the admin).
    :type job: Job
    :param store: Where the job's uploaded files are kept.
    :type store: ArtifactStore
    :return: Its content.
    :rtype: PlainTextResponse
    :raises HTTPException: 404 unless the job uploaded it.
    """
    content = await job_service.read_job_file(store, job, name)
    if content is None:
        raise not_found(FILE_KIND, name)
    return PlainTextResponse(content, headers=NEVER_A_PAGE)
