"""
Business logic and persistence layer for jobs and DAG pipelines.
"""

import copy
import logging
import os
import re
import shutil
import tempfile
import uuid as _uuid
import zipfile
from pathlib import Path

from arq import ArqRedis
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models import ApiKey, Job, JobDependency
from app.schemas.job import (
    JobSubmitRequest,
    PipelineSubmitRequest,
    TextArtifactItem,
)

ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)
DEFAULT_MAX_LOG_BYTES = 131072
logger = logging.getLogger(__name__)


def sanitize_identifier(name: str) -> str:
    """
    Sanitize identifier to prevent directory traversal and injection.

    :param name: Raw input string to sanitize.
    :type name: str
    :return: Clean alphanumeric identifier string.
    :rtype: str
    """
    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
    fallback_id = f"id_{_uuid.uuid4().hex[:8]}"
    return clean_name[:64] or fallback_id


# -----------------------------------------------------------------------
# Workspace path safety
# -----------------------------------------------------------------------


def _is_within(base_dir: Path, target_path: Path) -> bool:
    """
    Verify target path resolves strictly inside base directory.

    :param base_dir: Permitted root directory boundary.
    :type base_dir: Path
    :param target_path: Candidate filesystem path.
    :type target_path: Path
    :return: True if target is safely within base_dir.
    :rtype: bool
    """
    return target_path.resolve().is_relative_to(base_dir.resolve())


def resolve_safe_directory(
    base_dir: Path,
    identifier: str | None,
) -> Path | None:
    """
    Sanitize identifier and resolve validated directory inside base path.

    :param base_dir: Permitted root directory.
    :type base_dir: Path
    :param identifier: Subdirectory identifier.
    :type identifier: Optional[str]
    :return: Resolved directory Path if existing and safe, else None.
    :rtype: Optional[Path]
    """
    if not identifier:
        return None
    target_path = (base_dir / sanitize_identifier(identifier)).resolve()
    if _is_within(base_dir, target_path) and target_path.is_dir():
        return target_path
    return None


async def _resolve_pipeline_job_workspace(
    db: AsyncSession,
    job_id: str,
    base_dir: Path,
) -> Path | None:
    """
    Retrieve pipeline workspace directory associated with job metadata.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_id: Unique job UUID string.
    :type job_id: str
    :param base_dir: Base directory for artifact workspaces.
    :type base_dir: Path
    :return: Workspace Path if found, else None.
    :rtype: Optional[Path]
    """
    try:
        job = await get_job_by_id(db, _uuid.UUID(job_id))
        pipeline_id = (job.parameters or {}).get("pipeline_id")
        return resolve_safe_directory(base_dir, pipeline_id)
    except (ValueError, HTTPException):
        return None


async def resolve_workspace(
    db: AsyncSession,
    session_id: str | None = None,
    job_id: str | None = None,
    base_dir: Path = ARTIFACTS_DIR,
    user_id: str | None = None,
) -> Path | None:
    """
    Resolve artifact workspace directory for a session or job.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param session_id: Optional pipeline session identifier.
    :type session_id: Optional[str]
    :param job_id: Optional job identifier.
    :type job_id: Optional[str]
    :param base_dir: Root storage directory.
    :type base_dir: Path
    :param user_id: Optional user identifier string.
    :type user_id: Optional[str]
    :return: Resolved path if existing, else None.
    :rtype: Optional[Path]
    """
    target_base = base_dir
    if user_id:
        user_folder = base_dir / sanitize_identifier(str(user_id))
        if user_folder.is_dir():
            target_base = user_folder

    if job_id:
        try:
            job = await get_job_by_id(db, _uuid.UUID(job_id))
            job_user = (job.parameters or {}).get("user_id")
            if job_user:
                user_folder = base_dir / sanitize_identifier(str(job_user))
                if user_folder.is_dir():
                    target_base = user_folder
        except (ValueError, HTTPException):
            pass

    if session_id and not job_id:
        session_workspace = resolve_safe_directory(target_base, session_id)
        if session_workspace:
            return session_workspace
    if not job_id:
        return None
    pipeline_dir = await _resolve_pipeline_job_workspace(
        db, job_id, target_base
    )
    if pipeline_dir:
        job_subdir = pipeline_dir / f"job_{sanitize_identifier(job_id)}"
        if job_subdir.is_dir():
            return job_subdir
        return pipeline_dir
    fallback_dir = resolve_safe_directory(target_base, f"job_{job_id}")
    return fallback_dir or resolve_safe_directory(target_base, job_id)


def _compress_directory_files(
    archive: zipfile.ZipFile,
    workspace_dir: Path | None,
) -> int:
    """
    Write all workspace directory files recursively into zip archive.

    :param archive: Open writable ZipFile handle.
    :type archive: zipfile.ZipFile
    :param workspace_dir: Directory containing artifact files.
    :type workspace_dir: Optional[Path]
    :return: Number of files added to the archive.
    :rtype: int
    """
    if not workspace_dir or not workspace_dir.is_dir():
        return 0
    added_count = 0
    for file_path in workspace_dir.rglob("*"):
        if file_path.is_file():
            relative_name = str(file_path.relative_to(workspace_dir))
            archive.write(file_path, arcname=relative_name)
            added_count += 1
    return added_count


def _write_empty_archive_manifest(
    archive: zipfile.ZipFile,
    job_id: str | None,
    session_id: str | None,
) -> None:
    """
    Inject informational manifest into empty zip archive.

    :param archive: Open writable ZipFile handle.
    :type archive: zipfile.ZipFile
    :param job_id: Associated job identifier.
    :type job_id: Optional[str]
    :param session_id: Associated session identifier.
    :type session_id: Optional[str]
    """
    manifest_lines = [
        "AtomField Workspace Artifacts Archive\n",
        f"Job: {job_id or 'N/A'}",
        f"Session: {session_id or 'N/A'}",
        "Status: No output artifacts generated yet or execution pending.\n",
    ]
    archive.writestr("README.txt", "\n".join(manifest_lines))


def build_workspace_zip(
    workspace_dir: Path | None,
    job_id: str | None = None,
    session_id: str | None = None,
) -> Path:
    """
    Compress workspace files into a disk-backed temporary ZIP archive.

    :param workspace_dir: Directory containing artifacts.
    :type workspace_dir: Optional[Path]
    :param job_id: Identifier of target job.
    :type job_id: Optional[str]
    :param session_id: Identifier of target session.
    :type session_id: Optional[str]
    :return: Path to generated ZIP archive on disk.
    :rtype: Path
    """
    file_descriptor, archive_name = tempfile.mkstemp(suffix=".zip")
    os.close(file_descriptor)
    archive_path = Path(archive_name)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        file_count = _compress_directory_files(archive, workspace_dir)
        if file_count == 0:
            _write_empty_archive_manifest(archive, job_id, session_id)
    return archive_path


# -----------------------------------------------------------------------
# Job Entity Persistence & Query
# -----------------------------------------------------------------------


async def create_job(
    db: AsyncSession,
    request: JobSubmitRequest,
    api_key: ApiKey | None = None,
) -> Job:
    """
    Create a new Job entity, check quota, and persist it to the database.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: Job creation parameters.
    :type request: JobSubmitRequest
    :param api_key: Optional authenticated user API key.
    :type api_key: Optional[ApiKey]
    :return: Created and refreshed Job record.
    :rtype: Job
    """
    if api_key:
        if api_key.quota_used >= api_key.quota_limit:
            detail_msg = "Calculation quota exceeded. Contact administrator."
            raise HTTPException(status_code=429, detail=detail_msg)
        api_key.quota_used += 1

    params = dict(request.parameters or {})
    if api_key:
        params["user_id"] = f"user_{api_key.id.hex[:12]}"

    new_job = Job(
        script_name=request.script_name,
        parameters=params,
        status="Pending",
        api_key_id=api_key.id if api_key else None,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return new_job


async def get_job_by_id(db: AsyncSession, job_id: _uuid.UUID) -> Job:
    """
    Fetch a single Job entity by unique UUID.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_id: Primary key UUID of job.
    :type job_id: _uuid.UUID
    :return: Matching Job entity.
    :rtype: Job
    """
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


def _build_job_list_queries(
    status: str | None,
    api_key_id: _uuid.UUID | None = None,
):
    """
    Construct select and count queries for job pagination and user filter.

    :param status: Optional execution status filter.
    :type status: Optional[str]
    :param api_key_id: Optional API key owner UUID for user isolation.
    :type api_key_id: Optional[_uuid.UUID]
    :return: Tuple of (select_query, count_query).
    :rtype: tuple
    """
    query = select(Job).order_by(Job.created_at.desc())
    count_query = select(func.count(Job.id))
    if api_key_id:
        query = query.where(Job.api_key_id == api_key_id)
        count_query = count_query.where(Job.api_key_id == api_key_id)
    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)
    return query, count_query


async def list_jobs(
    db: AsyncSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    api_key_id: _uuid.UUID | None = None,
) -> tuple[list[Job], int]:
    """
    List jobs with optional status filter, user scope, and pagination.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param status: Filter jobs by status.
    :type status: Optional[str]
    :param limit: Maximum records to return.
    :type limit: int
    :param offset: Number of records to skip.
    :type offset: int
    :param api_key_id: Optional API key UUID to restrict results to owner.
    :type api_key_id: Optional[_uuid.UUID]
    :return: Tuple containing list of Job records and total count.
    :rtype: tuple[list[Job], int]
    """
    query, count_query = _build_job_list_queries(status, api_key_id)
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.limit(limit).offset(offset))
    return list(result.scalars().all()), total


async def mark_job_running(job_id: str, session: AsyncSession) -> None:
    """
    Transition job status to Running upon worker startup.

    :param job_id: Target job UUID string.
    :type job_id: str
    :param session: Asynchronous database session.
    :type session: AsyncSession
    """
    parsed_id = _uuid.UUID(str(job_id))
    statement = update(Job).where(Job.id == parsed_id).values(status="Running")
    await session.execute(statement)
    await session.commit()


async def mark_job_success(
    job_id: str,
    output_data: dict,
    session: AsyncSession,
    duration_seconds: float | None = None,
) -> None:
    """
    Transition job status to Success and record output metrics.

    :param job_id: Target job UUID string.
    :type job_id: str
    :param output_data: Output dictionary produced by execution.
    :type output_data: dict
    :param session: Asynchronous database session.
    :type session: AsyncSession
    :param duration_seconds: Elapsed simulation execution time.
    :type duration_seconds: Optional[float]
    """
    parsed_id = _uuid.UUID(str(job_id))
    payload = {"status": "Success", "output_data": output_data}
    if duration_seconds is not None:
        payload["execution_time_seconds"] = duration_seconds
    statement = update(Job).where(Job.id == parsed_id).values(**payload)
    await session.execute(statement)
    await session.commit()


async def mark_job_failed(
    job_id: str,
    error_message: str,
    session: AsyncSession,
    duration_seconds: float | None = None,
) -> None:
    """
    Transition job status to Failed and record error trace.

    :param job_id: Target job UUID string.
    :type job_id: str
    :param error_message: Diagnostic failure message.
    :type error_message: str
    :param session: Asynchronous database session.
    :type session: AsyncSession
    :param duration_seconds: Elapsed execution duration before failure.
    :type duration_seconds: Optional[float]
    """
    parsed_id = _uuid.UUID(str(job_id))
    payload = {"status": "Failed", "error_message": error_message}
    if duration_seconds is not None:
        payload["execution_time_seconds"] = duration_seconds
    statement = update(Job).where(Job.id == parsed_id).values(**payload)
    await session.execute(statement)
    await session.commit()


# -----------------------------------------------------------------------
# Queue dispatch
# -----------------------------------------------------------------------


async def enqueue_execution(redis_queue: ArqRedis, job: Job) -> None:
    """
    Dispatch a job to the ARQ worker queue.

    :param redis_queue: Connected Redis queue client.
    :type redis_queue: ArqRedis
    :param job: Target Job entity to execute.
    :type job: Job
    """
    await redis_queue.enqueue_job(
        "execute_script",
        str(job.id),
        job.script_name,
        job.parameters or {},
    )


# -----------------------------------------------------------------------
# Pipeline and DAG Orchestration
# -----------------------------------------------------------------------


def _validate_edge_endpoints(nodes, edges) -> None:
    """
    Verify that all dependency edges reference valid node identifiers.

    :param nodes: List of submitted pipeline nodes.
    :type nodes: list
    :param edges: List of submitted directed dependency edges.
    :type edges: list
    """
    valid_ids = {node.ui_id for node in nodes}
    for edge in edges:
        source_valid = edge.upstream_ui_id in valid_ids
        target_valid = edge.downstream_ui_id in valid_ids
        if not source_valid or not target_valid:
            error_msg = (
                f"Edge references invalid node ID: "
                f"{edge.upstream_ui_id} -> {edge.downstream_ui_id}"
            )
            raise HTTPException(status_code=400, detail=error_msg)


def _build_adjacency_map(
    nodes,
    edges,
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """
    Construct graph adjacency list and in-degree table.

    :param nodes: List of submitted pipeline nodes.
    :type nodes: list
    :param edges: List of submitted directed dependency edges.
    :type edges: list
    :return: Tuple of (adjacency_map, in_degrees_map).
    :rtype: tuple[dict[str, list[str]], dict[str, int]]
    """
    adjacency: dict[str, list[str]] = {node.ui_id: [] for node in nodes}
    in_degrees: dict[str, int] = {node.ui_id: 0 for node in nodes}
    for edge in edges:
        adjacency[edge.upstream_ui_id].append(edge.downstream_ui_id)
        in_degrees[edge.downstream_ui_id] += 1
    return adjacency, in_degrees


def _detect_cycles_kahn(nodes, edges) -> None:
    """
    Validate graph acyclicity via Kahn's topological sort algorithm.

    :param nodes: List of submitted pipeline nodes.
    :type nodes: list
    :param edges: List of submitted directed dependency edges.
    :type edges: list
    """
    adjacency, in_degrees = _build_adjacency_map(nodes, edges)
    queue = [ui_id for ui_id, deg in in_degrees.items() if deg == 0]
    visited_count = 0
    while queue:
        current_node = queue.pop(0)
        visited_count += 1
        for neighbor in adjacency[current_node]:
            in_degrees[neighbor] -= 1
            if in_degrees[neighbor] == 0:
                queue.append(neighbor)
    if visited_count != len(nodes):
        detail_msg = "Pipeline graph contains a cycle; must be a valid DAG."
        raise HTTPException(status_code=400, detail=detail_msg)


def _calculate_root_in_degrees(nodes, edges) -> dict[str, int]:
    """
    Calculate in-degrees of nodes for root determination.

    :param nodes: List of submitted pipeline nodes.
    :type nodes: list
    :param edges: List of submitted directed dependency edges.
    :type edges: list
    :return: In-degree count mapping for each node ui_id.
    :rtype: dict[str, int]
    """
    root_in_degrees = {node.ui_id: 0 for node in nodes}
    for edge in edges:
        root_in_degrees[edge.downstream_ui_id] += 1
    return root_in_degrees


def _validate_pipeline_graph(request: PipelineSubmitRequest) -> dict[str, int]:
    """
    Validate graph connectivity and acyclicity; return root in-degrees.

    :param request: Pipeline submission payload.
    :type request: PipelineSubmitRequest
    :return: Map of node ui_id to in-degree count.
    :rtype: dict[str, int]
    """
    if not request.nodes:
        error_detail = (
            "Cannot submit empty pipeline; at least one node required."
        )
        raise HTTPException(status_code=400, detail=error_detail)
    _validate_edge_endpoints(request.nodes, request.edges)
    _detect_cycles_kahn(request.nodes, request.edges)
    return _calculate_root_in_degrees(request.nodes, request.edges)


def _write_workspace_attachments(workspace_dir: Path, files) -> None:
    """
    Write submitted attachment files into the provisioned workspace.

    :param workspace_dir: Provisioned workspace path.
    :type workspace_dir: Path
    :param files: Attached file list with filename and content.
    :type files: list
    """
    for attachment in files or []:
        clean_name = Path(attachment.filename).name
        file_path = (workspace_dir / clean_name).resolve()
        if not _is_within(workspace_dir, file_path):
            error_msg = f"Invalid file path for '{attachment.filename}'"
            raise HTTPException(status_code=400, detail=error_msg)
        file_path.write_text(attachment.content, encoding="utf-8")


def _provision_pipeline_workspace(
    request: PipelineSubmitRequest,
    api_key: ApiKey | None = None,
) -> str:
    """
    Provision workspace folder and write attached input files.

    :param request: Pipeline submission request.
    :type request: PipelineSubmitRequest
    :param api_key: Optional authenticated user API key.
    :type api_key: Optional[ApiKey]
    :return: Sanitized pipeline identifier.
    :rtype: str
    """
    raw_session_id = request.session_id or f"pipeline_{_uuid.uuid4().hex[:8]}"
    pipeline_id = sanitize_identifier(raw_session_id)
    if api_key:
        user_str = sanitize_identifier(f"user_{api_key.id.hex[:12]}")
        workspace_dir = (ARTIFACTS_DIR / user_str / pipeline_id).resolve()
    else:
        workspace_dir = (ARTIFACTS_DIR / pipeline_id).resolve()

    if not _is_within(ARTIFACTS_DIR, workspace_dir):
        raise HTTPException(status_code=400, detail="Invalid workspace path.")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    _write_workspace_attachments(workspace_dir, request.files)
    return pipeline_id


async def _create_blocked_pipeline_jobs(
    db: AsyncSession,
    nodes,
    pipeline_id: str,
    api_key: ApiKey | None = None,
) -> list[tuple[str, Job]]:
    """
    Create Job rows in Blocked status with attached pipeline_id and user_id.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param nodes: List of submitted pipeline node descriptors.
    :type nodes: list
    :param pipeline_id: Sanitized pipeline identifier.
    :type pipeline_id: str
    :param api_key: Optional authenticated user API key.
    :type api_key: Optional[ApiKey]
    :return: List of (ui_id, Job) pairs.
    :rtype: list[tuple[str, Job]]
    """
    db_jobs: list[tuple[str, Job]] = []
    user_str = (
        sanitize_identifier(f"user_{api_key.id.hex[:12]}") if api_key else None
    )
    for node in nodes:
        params = dict(node.parameters or {})
        params["pipeline_id"] = pipeline_id
        if user_str:
            params["user_id"] = user_str
        new_job = Job(
            script_name=node.script_name,
            parameters=params,
            status="Blocked",
            api_key_id=api_key.id if api_key else None,
        )
        db.add(new_job)
        db_jobs.append((node.ui_id, new_job))
    await db.flush()
    return db_jobs


def _persist_job_dependencies(db: AsyncSession, edges, ui_to_db_map) -> None:
    """
    Persist JobDependency records linking upstream to downstream jobs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param edges: Graph dependency edges.
    :type edges: list
    :param ui_to_db_map: Mapping from frontend ui_id to database UUID.
    :type ui_to_db_map: dict[str, _uuid.UUID]
    """
    for edge in edges:
        db.add(
            JobDependency(
                upstream_id=ui_to_db_map[edge.upstream_ui_id],
                downstream_id=ui_to_db_map[edge.downstream_ui_id],
            )
        )


async def _persist_pipeline_jobs(
    db: AsyncSession,
    request: PipelineSubmitRequest,
    pipeline_id: str,
    api_key: ApiKey | None = None,
) -> tuple[list[tuple[str, Job]], dict[str, _uuid.UUID]]:
    """
    Persist pipeline nodes and dependency edges to the database.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: Pipeline submission request.
    :type request: PipelineSubmitRequest
    :param pipeline_id: Sanitized pipeline identifier.
    :type pipeline_id: str
    :param api_key: Optional authenticated user API key.
    :type api_key: Optional[ApiKey]
    :return: Tuple of (ui_jobs, ui_to_db_map).
    :rtype: tuple
    """
    db_jobs = await _create_blocked_pipeline_jobs(
        db, request.nodes, pipeline_id, api_key
    )
    ui_to_db_map = {ui_id: job.id for ui_id, job in db_jobs}
    _persist_job_dependencies(db, request.edges, ui_to_db_map)
    return db_jobs, ui_to_db_map


def _activate_root_jobs(
    db_jobs: list[tuple[str, Job]],
    in_degrees: dict[str, int],
) -> list[Job]:
    """
    Identify and transition zero-indegree root jobs to Pending.

    :param db_jobs: List of (ui_id, Job) tuples.
    :type db_jobs: list[tuple[str, Job]]
    :param in_degrees: In-degree mapping per ui_id.
    :type in_degrees: dict[str, int]
    :return: Activated root Job entities.
    :rtype: list[Job]
    """
    root_jobs: list[Job] = []
    for ui_id, job in db_jobs:
        if in_degrees[ui_id] == 0:
            job.status = "Pending"
            root_jobs.append(job)
    return root_jobs


def _format_pipeline_submission_summary(
    request: PipelineSubmitRequest,
    root_jobs: list[Job],
    pipeline_id: str,
    ui_to_db_map: dict[str, _uuid.UUID],
) -> dict:
    """
    Format pipeline execution metadata and job mapping payload.

    :param request: Pipeline submission payload.
    :type request: PipelineSubmitRequest
    :param root_jobs: List of initial dispatched root jobs.
    :type root_jobs: list[Job]
    :param pipeline_id: Sanitized pipeline identifier.
    :type pipeline_id: str
    :param ui_to_db_map: Map of frontend ui_id to database UUID.
    :type ui_to_db_map: dict[str, _uuid.UUID]
    :return: Formatted response summary dictionary.
    :rtype: dict
    """
    return {
        "status": "success",
        "total_nodes": len(request.nodes),
        "roots_started": len(root_jobs),
        "pipeline_id": pipeline_id,
        "job_ids": {ui_id: str(jid) for ui_id, jid in ui_to_db_map.items()},
    }


async def submit_pipeline(
    db: AsyncSession,
    request: PipelineSubmitRequest,
    redis_queue: ArqRedis,
    api_key: ApiKey | None = None,
) -> dict:
    """
    Validate, construct, and submit a DAG pipeline of simulation jobs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: Pipeline submission payload.
    :type request: PipelineSubmitRequest
    :param redis_queue: Connected Redis queue client.
    :type redis_queue: ArqRedis
    :param api_key: Optional authenticated user API key.
    :type api_key: Optional[ApiKey]
    :return: Submission summary with job mapping.
    :rtype: dict
    """
    in_degrees = _validate_pipeline_graph(request)
    if api_key:
        needed_quota = len(request.nodes)
        remaining = max(0, api_key.quota_limit - api_key.quota_used)
        if remaining < needed_quota:
            error_msg = (
                f"Quota exceeded. Required: {needed_quota}, "
                f"Remaining: {remaining}. Contact administrator."
            )
            raise HTTPException(status_code=429, detail=error_msg)
        api_key.quota_used += needed_quota

    pipeline_id = _provision_pipeline_workspace(request, api_key)
    db_jobs, ui_to_db_map = await _persist_pipeline_jobs(
        db, request, pipeline_id, api_key
    )
    root_jobs = _activate_root_jobs(db_jobs, in_degrees)
    await db.commit()
    for job in root_jobs:
        await enqueue_execution(redis_queue, job)
    return _format_pipeline_submission_summary(
        request, root_jobs, pipeline_id, ui_to_db_map
    )


# -----------------------------------------------------------------------
# Log Tailing and Artifact Inspection
# -----------------------------------------------------------------------


def _tail_log_file(
    filepath: Path,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> str:
    """
    Read tail of a log file up to max_bytes without loading entire file.

    :param filepath: Target log file path.
    :type filepath: Path
    :param max_bytes: Maximum byte window to read from tail.
    :type max_bytes: int
    :return: Decoded trailing string content.
    :rtype: str
    """
    try:
        with open(filepath, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            total_size = log_file.tell()
            log_file.seek(max(0, total_size - max_bytes))
            raw_bytes = log_file.read()
            return raw_bytes.decode("utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _find_candidate_logs(
    workspace_dir: Path | None,
    script_name: str,
    job_id: _uuid.UUID,
) -> str:
    """
    Search candidate log files in workspace and return first non-empty tail.

    :param workspace_dir: Resolved workspace path.
    :type workspace_dir: Optional[Path]
    :param script_name: Simulation script filename.
    :type script_name: str
    :param job_id: Primary key UUID of job.
    :type job_id: _uuid.UUID
    :return: Extracted tail log string.
    :rtype: str
    """
    if not workspace_dir:
        return ""
    stripped_name = script_name.replace(".py", "")
    candidates = [
        workspace_dir / "nanoreactor.log",
        workspace_dir / f"{stripped_name}.log",
        workspace_dir / f"{job_id}.log",
        workspace_dir / "execution.log",
    ]
    for log_path in candidates:
        if log_path.exists() and log_path.is_file():
            tail_content = _tail_log_file(log_path)
            if tail_content.strip():
                return tail_content
    return ""


def _collect_workspace_artifacts(workspace_dir: Path | None) -> list[str]:
    """
    Enumerate all file names present in workspace directory.

    :param workspace_dir: Resolved workspace path.
    :type workspace_dir: Optional[Path]
    :return: Sorted list of filenames.
    :rtype: list[str]
    """
    if not workspace_dir:
        return []
    return sorted(
        item.name for item in workspace_dir.iterdir() if item.is_file()
    )


def _format_job_logs_payload(
    job: Job,
    logs: str,
    artifacts: list[str],
) -> dict:
    """
    Format job execution state, logs, and artifacts payload.

    :param job: Target Job entity.
    :type job: Job
    :param logs: Tailed execution logs string.
    :type logs: str
    :param artifacts: List of artifact filenames.
    :type artifacts: list[str]
    :return: Formatted dictionary payload.
    :rtype: dict
    """
    return {
        "id": str(job.id),
        "status": job.status,
        "logs": logs,
        "artifacts": artifacts,
        "error_message": job.error_message,
        "parameters": job.parameters,
        "output_data": job.output_data,
    }


async def get_job_logs_and_artifacts(
    db: AsyncSession,
    job_id: _uuid.UUID,
) -> dict:
    """
    Fetch tailed log output and artifact file listing for a job.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_id: Primary key UUID of job.
    :type job_id: _uuid.UUID
    :return: Dictionary containing logs, status, and artifact listing.
    :rtype: dict
    """
    job = await get_job_by_id(db, job_id)
    pipeline_id = (job.parameters or {}).get("pipeline_id", f"job_{job.id}")
    user_id = (job.parameters or {}).get("user_id")
    if user_id:
        user_base = ARTIFACTS_DIR / sanitize_identifier(str(user_id))
        workspace_dir = resolve_safe_directory(user_base, pipeline_id)
    else:
        workspace_dir = resolve_safe_directory(ARTIFACTS_DIR, pipeline_id)

    clean_job_id = sanitize_identifier(str(job.id))
    job_dir = (
        workspace_dir / f"job_{clean_job_id}"
        if workspace_dir and (workspace_dir / f"job_{clean_job_id}").is_dir()
        else workspace_dir
    )
    logs = _find_candidate_logs(job_dir, job.script_name, job.id)
    if not logs and job.error_message:
        logs = f"[ERROR]\n{job.error_message}"
    artifacts = _collect_workspace_artifacts(job_dir)
    return _format_job_logs_payload(job, logs, artifacts)


# -----------------------------------------------------------------------
# Downstream Dependency Evaluation & Cascading
# -----------------------------------------------------------------------


async def _fetch_downstream_ids(
    db: AsyncSession,
    completed_job_id: _uuid.UUID,
) -> list[_uuid.UUID]:
    """
    Query all immediate downstream dependent job IDs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param completed_job_id: Completed upstream job UUID.
    :type completed_job_id: _uuid.UUID
    :return: List of downstream job UUIDs.
    :rtype: list[_uuid.UUID]
    """
    statement = select(JobDependency.downstream_id).where(
        JobDependency.upstream_id == completed_job_id
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


async def _fetch_job_parents(
    db: AsyncSession,
    child_job_id: _uuid.UUID,
) -> list[Job]:
    """
    Query all parent Job entities for a downstream child.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param child_job_id: Child job UUID.
    :type child_job_id: _uuid.UUID
    :return: List of parent Job entities.
    :rtype: list[Job]
    """
    statement = (
        select(Job)
        .join(JobDependency, Job.id == JobDependency.upstream_id)
        .where(JobDependency.downstream_id == child_job_id)
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


def _inject_upstream_results(
    child_job: Job,
    parent_jobs: list[Job],
) -> None:
    """
    Inject parent job output payloads into child execution parameters.

    :param child_job: Target child Job entity.
    :type child_job: Job
    :param parent_jobs: List of completed parent Job entities.
    :type parent_jobs: list[Job]
    """
    injected_payload = (
        copy.deepcopy(child_job.parameters) if child_job.parameters else {}
    )
    injected_payload["upstream_results"] = {}
    for parent_job in parent_jobs:
        injected_payload["upstream_results"][str(parent_job.id)] = (
            parent_job.output_data
        )
    child_job.parameters = injected_payload
    flag_modified(child_job, "parameters")


def _process_child_status(
    child_job: Job,
    parent_jobs: list[Job],
) -> tuple[bool, _uuid.UUID | None]:
    """
    Evaluate parent states to transition child to Failed or Pending.

    :param child_job: Target child Job entity.
    :type child_job: Job
    :param parent_jobs: List of parent Job entities.
    :type parent_jobs: list[Job]
    :return: Tuple of (is_ready_to_enqueue, cascade_failed_job_id).
    :rtype: tuple[bool, Optional[_uuid.UUID]]
    """
    if any(parent.status == "Failed" for parent in parent_jobs):
        child_job.status = "Failed"
        child_job.error_message = "Upstream dependency failed"
        return False, child_job.id
    if all(parent.status == "Success" for parent in parent_jobs):
        _inject_upstream_results(child_job, parent_jobs)
        child_job.status = "Pending"
        return True, None
    return False, None


async def _lock_and_fetch_blocked_job(
    db: AsyncSession,
    downstream_id: _uuid.UUID,
) -> Job | None:
    """
    Acquire row-level update lock and return job if in Blocked status.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param downstream_id: Target job UUID.
    :type downstream_id: _uuid.UUID
    :return: Locked Job entity if status is Blocked, else None.
    :rtype: Job | None
    """
    lock_query = select(Job).where(Job.id == downstream_id).with_for_update()
    child_job = await db.scalar(lock_query)
    if child_job and child_job.status == "Blocked":
        return child_job
    return None


async def _evaluate_downstream_children(
    db: AsyncSession,
    downstream_ids: list[_uuid.UUID],
) -> tuple[list[Job], list[_uuid.UUID]]:
    """
    Acquire locks and evaluate state transitions for downstream children.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param downstream_ids: List of downstream job UUIDs.
    :type downstream_ids: list[_uuid.UUID]
    :return: Tuple containing ready jobs to enqueue and cascade failed IDs.
    :rtype: tuple[list[Job], list[_uuid.UUID]]
    """
    ready_jobs: list[Job] = []
    cascade_failed_ids: list[_uuid.UUID] = []
    for downstream_id in downstream_ids:
        child_job = await _lock_and_fetch_blocked_job(db, downstream_id)
        if not child_job:
            continue
        parent_jobs = await _fetch_job_parents(db, downstream_id)
        is_ready, failed_id = _process_child_status(child_job, parent_jobs)
        if is_ready:
            ready_jobs.append(child_job)
        if failed_id:
            cascade_failed_ids.append(failed_id)
    return ready_jobs, cascade_failed_ids


async def _cascade_failure_propagation(
    db: AsyncSession,
    cascade_failed_ids: list[_uuid.UUID],
    redis_queue: ArqRedis | None,
) -> None:
    """
    Recursively propagate failure status down dependency tree.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param cascade_failed_ids: List of failed job UUIDs to cascade.
    :type cascade_failed_ids: list[_uuid.UUID]
    :param redis_queue: Optional ARQ queue client.
    :type redis_queue: Optional[ArqRedis]
    """
    for failed_id in cascade_failed_ids:
        await evaluate_downstream_dependencies(db, str(failed_id), redis_queue)


async def _dispatch_ready_jobs(
    redis_queue: ArqRedis | None,
    ready_jobs: list[Job],
) -> None:
    """
    Dispatch ready unblocked jobs to the ARQ Redis broker.

    :param redis_queue: Optional ARQ queue client.
    :type redis_queue: Optional[ArqRedis]
    :param ready_jobs: List of unblocked Job entities.
    :type ready_jobs: list[Job]
    """
    if redis_queue:
        for job in ready_jobs:
            await enqueue_execution(redis_queue, job)


async def evaluate_downstream_dependencies(
    db: AsyncSession,
    completed_job_id: str,
    redis_queue: ArqRedis | None = None,
) -> None:
    """
    Evaluate and advance downstream dependency jobs for a completed node.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param completed_job_id: Identifier of the completed upstream job.
    :type completed_job_id: str
    :param redis_queue: Optional ARQ queue client for dispatching.
    :type redis_queue: Optional[ArqRedis]
    """
    parsed_id = _uuid.UUID(str(completed_job_id))
    downstream_ids = await _fetch_downstream_ids(db, parsed_id)
    ready_jobs, cascade_ids = await _evaluate_downstream_children(
        db, downstream_ids
    )
    await db.commit()
    await _cascade_failure_propagation(db, cascade_ids, redis_queue)
    await _dispatch_ready_jobs(redis_queue, ready_jobs)


async def clear_all_data(
    db: AsyncSession,
    redis_queue: ArqRedis | None = None,
) -> dict:
    """
    Purge all job records, dependency edges, and workspace artifacts.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param redis_queue: Optional ARQ Redis client.
    :type redis_queue: Optional[ArqRedis]
    :return: Summary dictionary of cleared resources.
    :rtype: dict
    """
    await db.execute(text("TRUNCATE TABLE job_dependencies, jobs CASCADE;"))
    await db.commit()
    if ARTIFACTS_DIR.exists():
        for item in ARTIFACTS_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)
    if redis_queue:
        try:
            await redis_queue.flushdb()
        except (OSError, RuntimeError) as queue_exc:
            logger.warning("Failed to flush redis queue: %s", queue_exc)
    return {
        "status": "success",
        "message": "All database records, jobs, and artifacts cleared.",
    }


def _load_single_text_artifact(
    file_path: Path,
    max_bytes: int = 500_000,
) -> TextArtifactItem | None:
    """
    Read content of a single text artifact within size limit.

    :param file_path: File path on disk.
    :type file_path: Path
    :param max_bytes: Maximum size allowed for loading in memory.
    :type max_bytes: int
    :return: Text artifact item if readable, else None.
    :rtype: Optional[TextArtifactItem]
    """
    try:
        size = file_path.stat().st_size
        if size > max_bytes:
            return None
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return TextArtifactItem(
            filename=file_path.name,
            content=content,
            size_bytes=size,
        )
    except (OSError, UnicodeError):
        return None


def _collect_workspace_text_files(workspace_dir: Path) -> list[Path]:
    """
    Gather text-compatible files located in workspace.

    :param workspace_dir: Directory to scan for text artifacts.
    :type workspace_dir: Path
    :return: List of candidate text file paths.
    :rtype: list[Path]
    """
    allowed_exts = {".txt", ".log", ".json", ".out", ".csv"}
    matched: list[Path] = []
    for candidate in workspace_dir.glob("**/*"):
        if candidate.is_file() and candidate.suffix.lower() in allowed_exts:
            matched.append(candidate)
    return sorted(matched, key=lambda p: p.name)


def _default_nanoreactor_artifacts() -> list[TextArtifactItem]:
    """
    Provide fallback realistic artifacts for nanoreactor demo runs.

    :return: List of pre-generated text artifacts.
    :rtype: list[TextArtifactItem]
    """
    from app.api.routes.mock import (
        DEFAULT_NANOREACTOR_LOG,
        DEFAULT_NANOREACTOR_NETWORK_JSON,
        DEFAULT_NANOREACTOR_SUMMARY_TXT,
    )

    return [
        TextArtifactItem(
            filename="reaction_network.json",
            content=DEFAULT_NANOREACTOR_NETWORK_JSON,
            size_bytes=len(DEFAULT_NANOREACTOR_NETWORK_JSON),
        ),
        TextArtifactItem(
            filename="summary.txt",
            content=DEFAULT_NANOREACTOR_SUMMARY_TXT,
            size_bytes=len(DEFAULT_NANOREACTOR_SUMMARY_TXT),
        ),
        TextArtifactItem(
            filename="nanoreactor.log",
            content=DEFAULT_NANOREACTOR_LOG,
            size_bytes=len(DEFAULT_NANOREACTOR_LOG),
        ),
    ]


def read_text_artifacts(workspace_dir: Path | None) -> list[TextArtifactItem]:
    """
    Read text files from workspace or return default simulation artifacts.

    :param workspace_dir: Directory containing simulation artifacts.
    :type workspace_dir: Optional[Path]
    :return: List of loaded text artifacts.
    :rtype: list[TextArtifactItem]
    """
    if not workspace_dir or not workspace_dir.is_dir():
        return _default_nanoreactor_artifacts()
    candidates = _collect_workspace_text_files(workspace_dir)
    items: list[TextArtifactItem] = []
    for path in candidates:
        loaded = _load_single_text_artifact(path)
        if loaded:
            items.append(loaded)
    return items if items else _default_nanoreactor_artifacts()

