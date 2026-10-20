"""
HTTP route handlers for simulation jobs and DAG pipelines.
"""

from pathlib import Path
from uuid import UUID

from arq import ArqRedis
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.dependencies import (
    get_current_api_key,
    get_optional_api_key,
    get_redis,
)
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.schemas.job import (
    JobListResponse,
    JobResponse,
    JobSubmitRequest,
    PipelineSubmitRequest,
    PipelineSubmitResponse,
    TextArtifactsResponse,
)
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# -----------------------------------------------------------------------
# Job submission
# -----------------------------------------------------------------------


@router.post("/submit", response_model=JobResponse, status_code=202)
async def submit_job(
    job_req: JobSubmitRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    """
    Submit a standalone simulation job to the queue.

    :param job_req: Parameters and script name for execution.
    :type job_req: JobSubmitRequest
    :param api_key: Authenticated user API key.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param redis: Connected Redis worker queue.
    :type redis: ArqRedis
    :return: Created Job entity with Pending status.
    :rtype: Job
    """
    job = await job_service.create_job(db=db, request=job_req, api_key=api_key)
    await job_service.enqueue_execution(redis, job)
    return job


@router.post(
    "/pipeline/submit",
    response_model=PipelineSubmitResponse,
    status_code=202,
)
async def submit_pipeline(
    pipeline_req: PipelineSubmitRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    """
    Submit a DAG pipeline of simulation jobs.

    :param pipeline_req: Graph nodes, edges, and attached input files.
    :type pipeline_req: PipelineSubmitRequest
    :param api_key: Authenticated user API key.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param redis: Connected Redis worker queue.
    :type redis: ArqRedis
    :return: Pipeline submission receipt and job ID mappings.
    :rtype: dict
    """
    return await job_service.submit_pipeline(
        db=db,
        request=pipeline_req,
        redis_queue=redis,
        api_key=api_key,
    )


@router.delete("/clear")
async def clear_all_jobs(
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    """
    Clear all jobs, dependency DAGs, database records, and artifacts.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param redis: Connected Redis worker queue.
    :type redis: ArqRedis
    :return: Operation confirmation payload.
    :rtype: dict
    """
    return await job_service.clear_all_data(db=db, redis_queue=redis)


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a session, including all its database jobs, dependencies, and artifacts.

    :param session_id: Pipeline session identifier.
    :type session_id: str
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Operation confirmation payload.
    :rtype: dict
    """
    return await job_service.delete_session(
        db=db,
        session_id=session_id,
        api_key_id=api_key.id if api_key else None,
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
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve job status and output metadata.

    :param job_id: Primary key UUID of target job.
    :type job_id: UUID
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Job entity containing execution status and output metrics.
    :rtype: Job
    """
    return await job_service.get_job_by_id(db=db, job_id=job_id)


@router.get("/{job_id}/logs")
async def get_job_logs(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch live logs and generated artifact file list for a job.

    :param job_id: Primary key UUID of target job.
    :type job_id: UUID
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Dictionary containing logs, status, and artifact listing.
    :rtype: dict
    """
    return await job_service.get_job_logs_and_artifacts(db=db, job_id=job_id)


# -----------------------------------------------------------------------
# Artifact downloads
# -----------------------------------------------------------------------


def _build_zip_response(
    archive_path: Path,
    identifier: str,
) -> FileResponse:
    """
    Construct a streamed ZIP FileResponse with background cleanup.

    :param archive_path: Temporary filesystem path of ZIP archive.
    :type archive_path: Path
    :param identifier: Session or job identifier for download naming.
    :type identifier: str
    :return: Configured FastAPI FileResponse.
    :rtype: FileResponse
    """
    clean_identifier = job_service.sanitize_identifier(identifier)[:16]
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"artifacts_{clean_identifier}.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


async def _artifact_archive_response(
    *,
    db: AsyncSession,
    session_id: str | None,
    job_id: str | None,
    api_key: ApiKey | None = None,
) -> FileResponse:
    """
    Resolve target workspace and stream it back as a disk-backed ZIP.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param session_id: Optional pipeline session identifier.
    :type session_id: str | None
    :param job_id: Optional job identifier.
    :type job_id: str | None
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :return: Streamed FileResponse binary archive.
    :rtype: FileResponse
    """
    user_id = f"user_{api_key.id.hex[:12]}" if api_key else None
    workspace_dir = await job_service.resolve_workspace(
        db=db,
        session_id=session_id,
        job_id=job_id,
        user_id=user_id,
    )
    archive_path = job_service.build_workspace_zip(
        workspace_dir=workspace_dir,
        job_id=job_id,
        session_id=session_id,
    )
    target_id = session_id or job_id or "workspace"
    return _build_zip_response(archive_path, target_id)


@router.get("/artifacts/download")
async def download_session_artifacts(
    session_id: str | None = None,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Download workspace artifacts for a session as a ZIP archive.

    :param session_id: Optional session identifier string.
    :type session_id: str | None
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Streamed ZIP archive file response.
    :rtype: FileResponse
    """
    return await _artifact_archive_response(
        db=db,
        session_id=session_id,
        job_id=None,
        api_key=api_key,
    )


@router.get("/{job_id}/artifacts/download")
async def download_job_artifacts(
    job_id: UUID,
    session_id: str | None = None,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Download workspace artifacts for a job (or its session) as a ZIP.

    :param job_id: Target job UUID.
    :type job_id: UUID
    :param session_id: Optional associated session identifier string.
    :type session_id: str | None
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Streamed ZIP archive file response.
    :rtype: FileResponse
    """
    return await _artifact_archive_response(
        db=db,
        session_id=session_id,
        job_id=str(job_id),
        api_key=api_key,
    )


@router.get("/artifacts/text", response_model=TextArtifactsResponse)
async def get_session_text_artifacts(
    session_id: str | None = None,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
) -> TextArtifactsResponse:
    """
    Fetch readable text artifacts from session workspace.

    :param session_id: Optional session identifier.
    :type session_id: Optional[str]
    :param api_key: Optional authenticated API key.
    :type api_key: Optional[ApiKey]
    :param db: Database session.
    :type db: AsyncSession
    :return: Structured text artifacts response.
    :rtype: TextArtifactsResponse
    """
    user_id = f"user_{api_key.id.hex[:12]}" if api_key else None
    workspace = await job_service.resolve_workspace(
        db=db, session_id=session_id, job_id=None, user_id=user_id
    )
    files = job_service.read_text_artifacts(workspace)
    return TextArtifactsResponse(session_id=session_id, files=files)


@router.get("/{job_id}/artifacts/text", response_model=TextArtifactsResponse)
async def get_job_text_artifacts(
    job_id: UUID,
    session_id: str | None = None,
    api_key: ApiKey | None = Depends(get_optional_api_key),
    db: AsyncSession = Depends(get_db),
) -> TextArtifactsResponse:
    """
    Fetch readable text artifacts for a specific job.

    :param job_id: Target job UUID.
    :type job_id: UUID
    :param session_id: Optional session identifier.
    :type session_id: Optional[str]
    :param api_key: Optional authenticated API key.
    :type api_key: Optional[ApiKey]
    :param db: Database session.
    :type db: AsyncSession
    :return: Structured text artifacts response.
    :rtype: TextArtifactsResponse
    """
    user_id = f"user_{api_key.id.hex[:12]}" if api_key else None
    workspace = await job_service.resolve_workspace(
        db=db, session_id=session_id, job_id=str(job_id), user_id=user_id
    )
    files = job_service.read_text_artifacts(workspace)
    return TextArtifactsResponse(
        session_id=session_id, job_id=str(job_id), files=files
    )

