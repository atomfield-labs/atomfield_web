"""
Business logic and persistence layer for jobs and DAG pipelines.
"""

import logging
import shutil
import uuid as _uuid
from pathlib import Path

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import EXECUTION_LOG
from app.core.config import settings
from app.core.identifiers import (
    assign_node_keys,
    sanitize_identifier,
    user_folder_name,
)
from app.models import ApiKey, Job, JobDependency, Run
from app.queue.job_queue import RedisJobQueue
from app.runs.lifecycle import create_run, dispatch
from app.runs.states import JobStatus
from app.schemas.job import (
    JobSubmitRequest,
    PipelineSubmitRequest,
)
from app.storage.keys import (
    RUNS,
    UPLOADS,
    job_file_key,
    owner_uploads_folder,
    run_files_folder,
    upload_folder,
    upload_key,
)
from app.storage.store import ArtifactStore, InvalidKeyError

ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)
DEFAULT_MAX_LOG_BYTES = 131072
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Job Entity Persistence & Query
# -----------------------------------------------------------------------


async def create_job(
    db: AsyncSession,
    request: JobSubmitRequest,
    queue: RedisJobQueue,
    api_key: ApiKey | None = None,
) -> Job:
    """
    Create a new Job entity, check quota, and persist it to the database.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: Job creation parameters.
    :type request: JobSubmitRequest
    :param queue: Job queue the new job is sent to after commit.
    :type queue: RedisJobQueue
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
        params["user_id"] = user_folder_name(api_key.id)

    owner_id = api_key.id if api_key else None
    job_id = _uuid.uuid4()
    run = await create_run(db, owner_id, f"job_{job_id}")
    new_job = Job(
        id=job_id,
        run_id=run.id,
        script_name=request.script_name,
        node_key=sanitize_identifier(request.script_name),
        parameters=params,
        input_files=request.inputs or None,
        status=JobStatus.QUEUED,
        api_key_id=owner_id,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    await dispatch(db, queue, [new_job])
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


# -----------------------------------------------------------------------
# Queue dispatch
# -----------------------------------------------------------------------


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


async def store_attachments(
    store: ArtifactStore,
    files,
    api_key: ApiKey | None,
    session_id: str,
) -> None:
    """
    Keep the files attached to a submission in the store, where agents
    fetch them through signed links.

    :param store: The server's file store.
    :type store: ArtifactStore
    :param files: Attachments (name and text content).
    :type files: list[PipelineSubmitFile] | None
    :param api_key: Submitting user.
    :type api_key: ApiKey | None
    :param session_id: Session the files belong to.
    :type session_id: str
    :raises HTTPException: 400 for a file name that is not plain.
    """
    owner_id = api_key.id if api_key else None
    for attachment in files or []:
        try:
            key = upload_key(owner_id, session_id, attachment.filename)
        except InvalidKeyError:
            detail = f"Invalid file name {attachment.filename!r}"
            raise HTTPException(status_code=400, detail=detail) from None
        await store.write(key, attachment.content.encode("utf-8"))


async def create_blocked_pipeline_jobs(
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
        sanitize_identifier(user_folder_name(api_key.id)) if api_key else None
    )
    run = await create_run(db, api_key.id if api_key else None, pipeline_id)
    node_keys = assign_node_keys([node.ui_id for node in nodes])
    for node in nodes:
        params = dict(node.parameters or {})
        params["pipeline_id"] = pipeline_id
        if user_str:
            params["user_id"] = user_str
        new_job = Job(
            script_name=node.script_name,
            node_key=node_keys[node.ui_id],
            parameters=params,
            input_files=node.inputs or None,
            run_id=run.id,
            status=JobStatus.WAITING,
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
    db_jobs = await create_blocked_pipeline_jobs(
        db, request.nodes, pipeline_id, api_key
    )
    ui_to_db_map = {ui_id: job.id for ui_id, job in db_jobs}
    _persist_job_dependencies(db, request.edges, ui_to_db_map)
    return db_jobs, ui_to_db_map


def set_initial_states(
    db_jobs: list[tuple[str, Job]],
    in_degrees: dict[str, int],
) -> list[Job]:
    """
    Give each job its count of parents; jobs with none start queued.

    :param db_jobs: List of (ui_id, Job) tuples.
    :type db_jobs: list[tuple[str, Job]]
    :param in_degrees: Number of parents per ui_id.
    :type in_degrees: dict[str, int]
    :return: The root jobs, ready to dispatch after commit.
    :rtype: list[Job]
    """
    for ui_id, job in db_jobs:
        job.pending_parents = in_degrees[ui_id]
        job.status = (
            JobStatus.WAITING if in_degrees[ui_id] else JobStatus.QUEUED
        )
    return [job for _, job in db_jobs if job.status == JobStatus.QUEUED]


def record_parents(
    db_jobs: list[tuple[str, Job]],
    edges,
    ui_to_db_map: dict[str, _uuid.UUID],
) -> None:
    """
    Note each job's parents in ``upstream_results``, for people reading
    the job. Agents get parents from the dependency table instead.

    :param db_jobs: List of (ui_id, Job) tuples.
    :type db_jobs: list[tuple[str, Job]]
    :param edges: Submitted dependency edges.
    :type edges: list
    :param ui_to_db_map: ui_id -> stored job id.
    :type ui_to_db_map: dict[str, _uuid.UUID]
    """
    parents: dict[str, dict[str, dict]] = {}
    for edge in edges:
        upstream_id = str(ui_to_db_map[edge.upstream_ui_id])
        parents.setdefault(edge.downstream_ui_id, {})[upstream_id] = {}
    for ui_id, job in db_jobs:
        if ui_id in parents:
            job.parameters = {
                **job.parameters,
                "upstream_results": parents[ui_id],
            }


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
        "run_id": root_jobs[0].run_id if root_jobs else None,
        "job_ids": {ui_id: str(jid) for ui_id, jid in ui_to_db_map.items()},
    }


async def submit_pipeline(
    db: AsyncSession,
    request: PipelineSubmitRequest,
    queue: RedisJobQueue,
    store: ArtifactStore,
    api_key: ApiKey | None = None,
) -> dict:
    """
    Validate, construct, and submit a DAG pipeline of simulation jobs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: Pipeline submission payload.
    :type request: PipelineSubmitRequest
    :param queue: Job queue the root jobs are sent to after commit.
    :type queue: RedisJobQueue
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

    pipeline_id = sanitize_identifier(
        request.session_id or f"pipeline_{_uuid.uuid4().hex[:8]}"
    )
    await store_attachments(store, request.files, api_key, pipeline_id)
    db_jobs, ui_to_db_map = await _persist_pipeline_jobs(
        db, request, pipeline_id, api_key
    )
    root_jobs = set_initial_states(db_jobs, in_degrees)
    record_parents(db_jobs, request.edges, ui_to_db_map)
    await db.commit()
    await dispatch(db, queue, root_jobs)
    return _format_pipeline_submission_summary(
        request, root_jobs, pipeline_id, ui_to_db_map
    )


# -----------------------------------------------------------------------
# Log Tailing and Artifact Inspection
# -----------------------------------------------------------------------


async def read_job_log(store: ArtifactStore, job: Job) -> str:
    """
    The end of a finished job's log, from the copy its agent uploaded:
    the script's own log if there is one, else the command's output.

    :param store: Where uploaded job files are kept.
    :type store: ArtifactStore
    :param job: The job.
    :type job: Job
    :return: Up to the last ``DEFAULT_MAX_LOG_BYTES`` of the log, or ""
        while the job runs (nothing is uploaded until it ends).
    :rtype: str
    """
    uploaded = {
        card["path"] for card in job.output_files or [] if card["uploaded"]
    }
    for name in (f"{job.script_name}.log", EXECUTION_LOG):
        if name in uploaded:
            data = await store.read(job_file_key(job.run_id, job.id, name))
            if data:
                return data[-DEFAULT_MAX_LOG_BYTES:].decode("utf-8", "ignore")
    return ""


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
    store: ArtifactStore,
    job_id: _uuid.UUID,
) -> dict:
    """
    A job's state, the end of its log, and the files it left.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where uploaded job files are kept.
    :type store: ArtifactStore
    :param job_id: The job.
    :type job_id: uuid.UUID
    :return: Status, log tail, file names and outputs.
    :rtype: dict
    """
    job = await get_job_by_id(db, job_id)
    logs = await read_job_log(store, job)
    if not logs and job.error_message:
        logs = f"[ERROR]\n{job.error_message}"
    artifacts = [card["path"] for card in job.output_files or []]
    return _format_job_logs_payload(job, logs, artifacts)


# -----------------------------------------------------------------------
# Downstream Dependency Evaluation & Cascading
# -----------------------------------------------------------------------


async def clear_all_data(
    db: AsyncSession,
    store: ArtifactStore,
    redis_queue: Redis | None = None,
) -> dict:
    """
    Purge every run, job and stored file (operator wipe).

    The house agent's run folders live on this server too and go with
    them; folders on users' own machines are theirs and never touched.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param redis_queue: Optional Redis client to flush.
    :type redis_queue: Optional[Redis]
    :return: Summary.
    :rtype: dict
    """
    await db.execute(
        text("TRUNCATE TABLE job_dependencies, jobs, runs CASCADE;")
    )
    await db.commit()
    for folder in (UPLOADS, RUNS):
        await store.delete_folder(folder)
    shutil.rmtree(ARTIFACTS_DIR, ignore_errors=True)
    if redis_queue:
        try:
            await redis_queue.flushdb()
        except (OSError, RuntimeError) as queue_exc:
            logger.warning("Failed to flush redis queue: %s", queue_exc)
    return {
        "status": "success",
        "message": "All runs, jobs and stored files cleared.",
    }


async def delete_jobs(db: AsyncSession, job_ids: list[_uuid.UUID]) -> None:
    """
    Delete jobs and every dependency edge that touches them.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_ids: Jobs to delete.
    :type job_ids: list[uuid.UUID]
    """
    if not job_ids:
        return
    touches_deleted = or_(
        JobDependency.upstream_id.in_(job_ids),
        JobDependency.downstream_id.in_(job_ids),
    )
    await db.execute(delete(JobDependency).where(touches_deleted))
    await db.execute(delete(Job).where(Job.id.in_(job_ids)))
    await db.commit()


async def delete_runs(
    db: AsyncSession,
    store: ArtifactStore,
    run_ids: list[_uuid.UUID],
) -> int:
    """
    Delete runs with their jobs, edges and stored files (UI files and
    zips). Files on the machines that ran them stay: they are the
    user's.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param run_ids: Runs to delete.
    :type run_ids: list[uuid.UUID]
    :return: How many jobs went with them.
    :rtype: int
    """
    query = select(Job.id).where(Job.run_id.in_(run_ids))
    job_ids = list((await db.execute(query)).scalars())
    await delete_jobs(db, job_ids)
    await db.execute(delete(Run).where(Run.id.in_(run_ids)))
    await db.commit()
    for run_id in run_ids:
        await store.delete_folder(run_files_folder(run_id))
    return len(job_ids)


async def delete_session(
    db: AsyncSession,
    store: ArtifactStore,
    session_id: str,
    api_key_id: _uuid.UUID,
) -> dict:
    """
    Delete one of the caller's sessions: its runs, jobs and files.

    Only the caller's runs and uploads are touched, never another
    user's that happen to share the session's name.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param session_id: Session to delete.
    :type session_id: str
    :param api_key_id: The caller.
    :type api_key_id: uuid.UUID
    :return: Summary.
    :rtype: dict
    """
    clean_session_id = sanitize_identifier(session_id)
    query = select(Run.id).where(
        Run.owner_id == api_key_id, Run.session_id == clean_session_id
    )
    run_ids = list((await db.execute(query)).scalars())
    deleted = await delete_runs(db, store, run_ids)
    await store.delete_folder(upload_folder(api_key_id, clean_session_id))
    return {
        "status": "success",
        "message": f"Session {clean_session_id} and {deleted} jobs deleted.",
    }


async def clear_user_data(
    db: AsyncSession,
    store: ArtifactStore,
    api_key_id: _uuid.UUID,
) -> dict:
    """
    Delete all of one user's runs, jobs and stored files.

    Other users' data and the shared queue are left alone; wiping the
    whole system is an operator task (``python -m app.cli wipe``).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param api_key_id: The caller.
    :type api_key_id: uuid.UUID
    :return: Summary.
    :rtype: dict
    """
    query = select(Run.id).where(Run.owner_id == api_key_id)
    run_ids = list((await db.execute(query)).scalars())
    deleted = await delete_runs(db, store, run_ids)
    await store.delete_folder(owner_uploads_folder(api_key_id))
    return {
        "status": "success",
        "message": f"Deleted your {deleted} jobs and their files.",
    }
