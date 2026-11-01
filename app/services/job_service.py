"""
Submitting jobs and pipelines, reading them back, and deleting them.

A submission arrives checked (``submission_validation`` checks each
task, ``pipeline_graph`` a pipeline's shape); here it is counted
against the user's quota, stored as one run of jobs with its files,
and the jobs with no parents are queued.
"""

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import ColumnElement, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import EXECUTION_LOG
from app.agents.targets import usable_target
from app.api.errors import too_many_requests
from app.core.config import settings
from app.core.identifiers import assign_node_keys, sanitize_identifier
from app.models import Job, JobDependency, PipelineSession, Run, User
from app.queue.job_queue import RedisJobQueue
from app.runs.lifecycle import create_run, dispatch
from app.runs.states import JobStatus
from app.schemas.job import (
    JobEdge,
    JobFileKind,
    JobFilesResponse,
    JobFileView,
    JobNode,
    JobSubmitRequest,
    PipelineFile,
    PipelineSubmitRequest,
)
from app.services.pipeline_graph import check_pipeline_graph
from app.services.sessions import record_run
from app.storage.keys import (
    RUNS,
    UPLOADS,
    job_file_key,
    owner_uploads_folder,
    run_files_folder,
    upload_folder,
    upload_key,
)
from app.storage.store import ArtifactStore

ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)
DEFAULT_MAX_LOG_BYTES = 131072
SUCCESS = "success"
# Which session a pipeline's job came from.
PIPELINE_ID = "pipeline_id"
QUOTA_MESSAGE = (
    "Quota exceeded: this submission needs {needed} and your quota has "
    "{remaining} left. Contact the administrator."
)
ERROR_LOG_HEADER = "[ERROR]"
# A script's plots, which the web app draws (see docs/releases.md).
PLOTS_SUFFIX = "_plots.json"
TRUNCATE_ALL = (
    "TRUNCATE TABLE job_dependencies, jobs, runs, pipeline_sessions CASCADE;"
)
WIPED_MESSAGE = "All runs, jobs and stored files cleared."
logger = logging.getLogger(__name__)


async def charge_quota(db: AsyncSession, user: User, needed: int) -> None:
    """
    Count ``needed`` jobs against the user's quota, or refuse them all.

    One conditional UPDATE, whose row lock lasts until the submission
    commits: two submissions at the same moment take turns, so they
    cannot both spend the last of a quota. Reading the count and then
    writing the new total would let each overwrite the other's.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param user: The submitting person.
    :type user: User
    :param needed: Jobs in the submission.
    :type needed: int
    :raises HTTPException: 429 if they do not fit.
    """
    fits = User.quota_used + needed <= User.quota_limit
    statement = (
        update(User)
        .where(User.id == user.id, fits)
        .values(quota_used=User.quota_used + needed)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    if (await db.execute(statement)).first() is None:
        await db.refresh(user)
        remaining = user.quota_remaining
        message = QUOTA_MESSAGE.format(needed=needed, remaining=remaining)
        raise too_many_requests(message)


async def start_run(
    db: AsyncSession,
    user: User,
    session_id: str,
    target_id: uuid.UUID | None,
    release_id: uuid.UUID | None,
) -> Run:
    """
    A new run of the user's, on the target they asked for (the shared
    server if none).

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param user: The submitting person.
    :type user: User
    :param session_id: The run's session.
    :type session_id: str
    :param target_id: The target asked for, if any.
    :type target_id: uuid.UUID | None
    :param release_id: Scripts release its jobs use.
    :type release_id: uuid.UUID | None
    :return: The run.
    :rtype: Run
    :raises HTTPException: 404 for a target the user may not use.
    """
    target = await usable_target(db, user.id, target_id)
    return await create_run(db, user.id, session_id, target, release_id)


def new_job(
    run: Run,
    request: JobSubmitRequest | JobNode,
    node_key: str,
    **columns: Any,
) -> Job:
    """
    A job of a run, as submitted.

    :param run: Its run.
    :type run: Run
    :param request: The job's task, parameters and input files.
    :type request: JobSubmitRequest | JobNode
    :param node_key: Its folder name, unique within the run.
    :type node_key: str
    :param columns: Its status, parameters and other columns.
    :type columns: Any
    :return: The job, not yet added to the session.
    :rtype: Job
    """
    return Job(
        run_id=run.id,
        owner_id=run.owner_id,
        script_name=request.script_name,
        node_key=node_key,
        input_files=request.inputs or None,
        **columns,
    )


def single_job(run: Run, request: JobSubmitRequest, job_id: uuid.UUID) -> Job:
    """
    The one job of a single-job run, queued at once.

    :param run: Its run.
    :type run: Run
    :param request: The job, checked.
    :type request: JobSubmitRequest
    :param job_id: Its id (the run's session is named after it).
    :type job_id: uuid.UUID
    :return: The job, not yet added to the session.
    :rtype: Job
    """
    return new_job(
        run,
        request,
        sanitize_identifier(request.script_name),
        id=job_id,
        parameters=dict(request.parameters),
        status=JobStatus.QUEUED,
    )


async def create_job(
    db: AsyncSession,
    request: JobSubmitRequest,
    queue: RedisJobQueue,
    user: User,
    release_id: uuid.UUID | None = None,
) -> Job:
    """
    Submit one job: a run of its own (session ``job_<id>``), queued at
    once.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: The job, checked.
    :type request: JobSubmitRequest
    :param queue: Job queue the job is sent to after commit.
    :type queue: RedisJobQueue
    :param user: The submitting person.
    :type user: User
    :param release_id: Scripts release the job runs (None: no release
        published yet).
    :type release_id: uuid.UUID | None
    :return: The stored job.
    :rtype: Job
    :raises HTTPException: 429 over the quota; 404 for a target the
        user may not use.
    """
    await charge_quota(db, user, 1)
    job_id = uuid.uuid4()
    run = await start_run(
        db, user, f"job_{job_id}", request.target_id, release_id
    )
    job = single_job(run, request, job_id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await dispatch(db, queue, [job])
    return job


async def list_jobs(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: JobStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """
    A page of the user's jobs, newest first, and how many there are.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user_id: The user.
    :type user_id: uuid.UUID
    :param status: Only jobs in this state, if given.
    :type status: JobStatus | None
    :param limit: Most jobs to return.
    :type limit: int
    :param offset: Jobs to skip.
    :type offset: int
    :return: The page, and the number of matching jobs.
    :rtype: tuple[list[Job], int]
    """
    conditions = [Job.owner_id == user_id]
    if status is not None:
        conditions.append(Job.status == status)
    counted = select(func.count(Job.id)).where(*conditions)
    total = (await db.execute(counted)).scalar_one()
    newest_first = Job.created_at.desc()
    query = select(Job).where(*conditions).order_by(newest_first)
    page = await db.execute(query.limit(limit).offset(offset))
    return list(page.scalars()), total


def session_name(session_id: str | None) -> str:
    """
    A pipeline's session: the one the web app named, made a plain
    identifier, or a new one.

    :param session_id: The session asked for, if any.
    :type session_id: str | None
    :return: The session's name.
    :rtype: str
    """
    return sanitize_identifier(session_id or f"pipeline_{uuid.uuid4().hex[:8]}")


def pipeline_job(run: Run, node: JobNode, node_key: str, parents: int) -> Job:
    """
    One job of a pipeline: waiting for its parents, or queued if it
    has none.

    :param run: The pipeline's run.
    :type run: Run
    :param node: The node, checked.
    :type node: JobNode
    :param node_key: Its folder name, unique within the run.
    :type node_key: str
    :param parents: How many parents it waits for.
    :type parents: int
    :return: The job, not yet added to the session.
    :rtype: Job
    """
    status = JobStatus.WAITING if parents else JobStatus.QUEUED
    parameters = {**node.parameters, PIPELINE_ID: run.session_id}
    return new_job(
        run,
        node,
        node_key,
        parameters=parameters,
        pending_parents=parents,
        status=status,
    )


def dependencies(
    jobs: dict[str, Job], edges: list[JobEdge]
) -> list[JobDependency]:
    """
    The rows linking each stored child to its parents.

    :param jobs: Node id -> stored job.
    :type jobs: dict[str, Job]
    :param edges: The pipeline's edges.
    :type edges: list[JobEdge]
    :return: One row per edge.
    :rtype: list[JobDependency]
    """
    return [
        JobDependency(
            upstream_id=jobs[edge.upstream_ui_id].id,
            downstream_id=jobs[edge.downstream_ui_id].id,
        )
        for edge in edges
    ]


def record_parents(jobs: dict[str, Job], edges: list[JobEdge]) -> None:
    """
    Note each job's parents in ``upstream_results``, for people reading
    the job. Agents get parents from the dependency table instead.

    :param jobs: Node id -> stored job.
    :type jobs: dict[str, Job]
    :param edges: The pipeline's edges.
    :type edges: list[JobEdge]
    """
    parents: dict[str, dict[str, dict]] = {}
    for edge in edges:
        parent_id = str(jobs[edge.upstream_ui_id].id)
        parents.setdefault(edge.downstream_ui_id, {})[parent_id] = {}
    for ui_id, found in parents.items():
        job = jobs[ui_id]
        job.parameters = {**job.parameters, "upstream_results": found}


async def add_pipeline_jobs(
    db: AsyncSession,
    run: Run,
    request: PipelineSubmitRequest,
    parent_counts: dict[str, int],
) -> dict[str, Job]:
    """
    Store a pipeline's jobs and the edges between them.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param run: The pipeline's run.
    :type run: Run
    :param request: The pipeline, checked.
    :type request: PipelineSubmitRequest
    :param parent_counts: Node id -> parents it waits for.
    :type parent_counts: dict[str, int]
    :return: Node id -> stored job.
    :rtype: dict[str, Job]
    """
    keys = assign_node_keys([node.ui_id for node in request.nodes])
    jobs = {
        node.ui_id: pipeline_job(
            run, node, keys[node.ui_id], parent_counts[node.ui_id]
        )
        for node in request.nodes
    }
    db.add_all(jobs.values())
    await db.flush()
    db.add_all(dependencies(jobs, request.edges))
    record_parents(jobs, request.edges)
    return jobs


async def store_attachments(
    store: ArtifactStore,
    files: list[PipelineFile] | None,
    run: Run,
) -> None:
    """
    Keep the files attached to a submission in the store, where agents
    fetch them through signed links. Their names were checked with the
    rest of the request, before anything was stored.

    :param store: The server's file store.
    :type store: ArtifactStore
    :param files: Attachments (name and text content).
    :type files: list[PipelineFile] | None
    :param run: The run they belong to (its owner and session).
    :type run: Run
    """
    for attachment in files or []:
        key = upload_key(run.owner_id, run.session_id, attachment.filename)
        await store.write(key, attachment.content.encode("utf-8"))


def submission_summary(
    request: PipelineSubmitRequest, run: Run, jobs: dict[str, Job]
) -> dict:
    """
    What the web app is told about a stored pipeline.

    :param request: The pipeline.
    :type request: PipelineSubmitRequest
    :param run: Its run.
    :type run: Run
    :param jobs: Node id -> stored job.
    :type jobs: dict[str, Job]
    :return: Counts, the run and session, and each node's job.
    :rtype: dict
    """
    roots = [job for job in jobs.values() if job.status == JobStatus.QUEUED]
    return {
        "status": SUCCESS,
        "total_nodes": len(request.nodes),
        "roots_started": len(roots),
        "pipeline_id": run.session_id,
        "run_id": run.id,
        "job_ids": {ui_id: str(job.id) for ui_id, job in jobs.items()},
    }


async def submit_pipeline(
    db: AsyncSession,
    request: PipelineSubmitRequest,
    queue: RedisJobQueue,
    store: ArtifactStore,
    user: User,
    release_id: uuid.UUID | None = None,
) -> dict:
    """
    Submit a pipeline: check its shape, count its jobs against the
    quota, store them as one run with their files, then queue the jobs
    with no parents. The files are stored last, so a refused target
    leaves none behind.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param request: The pipeline, its tasks checked.
    :type request: PipelineSubmitRequest
    :param queue: Job queue the first jobs are sent to after commit.
    :type queue: RedisJobQueue
    :param store: Where attached files are kept.
    :type store: ArtifactStore
    :param user: The submitting person.
    :type user: User
    :param release_id: Scripts release the run is pinned to.
    :type release_id: uuid.UUID | None
    :return: Submission summary with each node's job.
    :rtype: dict
    :raises HTTPException: 400 for a bad graph, 429 over the quota, 404
        for a target the user may not use.
    """
    parent_counts = check_pipeline_graph(request)
    await charge_quota(db, user, len(request.nodes))
    session = session_name(request.session_id)
    run = await start_run(db, user, session, request.target_id, release_id)
    jobs = await add_pipeline_jobs(db, run, request, parent_counts)
    await store_attachments(store, request.files, run)
    await record_run(db, run, jobs)
    await db.commit()
    summary = submission_summary(request, run, jobs)
    roots = [job for job in jobs.values() if job.status == JobStatus.QUEUED]
    await dispatch(db, queue, roots)
    return summary


def uploaded_names(job: Job) -> set[str]:
    """
    The files of a job whose agent uploaded a copy.

    :param job: The job.
    :type job: Job
    :return: Their names; none while the job runs.
    :rtype: set[str]
    """
    return {card["path"] for card in job.output_files or [] if card["uploaded"]}


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
    uploaded = uploaded_names(job)
    for name in (f"{job.script_name}.log", EXECUTION_LOG):
        if name in uploaded:
            data = await store.read(job_file_key(job.run_id, job.id, name))
            if data:
                return data[-DEFAULT_MAX_LOG_BYTES:].decode("utf-8", "ignore")
    return ""


async def job_logs_and_files(store: ArtifactStore, job: Job) -> dict:
    """
    A job's state, the end of its log (or its error), and its files.

    :param store: Where uploaded job files are kept.
    :type store: ArtifactStore
    :param job: The job.
    :type job: Job
    :return: Status, log tail, file names and outputs.
    :rtype: dict
    """
    logs = await read_job_log(store, job)
    if not logs and job.error_message:
        logs = f"{ERROR_LOG_HEADER}\n{job.error_message}"
    return {
        "id": str(job.id),
        "status": job.status,
        "logs": logs,
        "artifacts": [card["path"] for card in job.output_files or []],
        "error_message": job.error_message,
        "parameters": job.parameters,
        "output_data": job.output_data,
    }


def job_files(job: Job) -> JobFilesResponse:
    """
    The files of a job the web app can show.

    :param job: The job.
    :type job: Job
    :return: The uploaded files, and how many others stay behind.
    :rtype: JobFilesResponse
    """
    cards = job.output_files or []
    shown = [
        JobFileView(
            name=card["path"],
            size_bytes=card["size_bytes"],
            kind=(
                JobFileKind.PLOTS
                if card["path"].endswith(PLOTS_SUFFIX)
                else JobFileKind.TEXT
            ),
        )
        for card in cards
        if card["uploaded"]
    ]
    return JobFilesResponse(files=shown, others=len(cards) - len(shown))


async def read_job_file(
    store: ArtifactStore, job: Job, name: str
) -> bytes | None:
    """
    The stored copy of one of a job's files.

    :param store: Where uploaded job files are kept.
    :type store: ArtifactStore
    :param job: The job.
    :type job: Job
    :param name: The file, as its card names it.
    :type name: str
    :return: Its content; None unless the job uploaded a file of that
        name, so nothing else in the store can be asked for.
    :rtype: bytes | None
    """
    if name not in uploaded_names(job):
        return None
    return await store.read(job_file_key(job.run_id, job.id, name))


async def empty_redis(redis: Redis) -> None:
    """
    Empty Redis: queued jobs, locks and counters. Not reaching it is
    worth only a warning: what it held described the database the wipe
    has just emptied.

    :param redis: The server's Redis.
    :type redis: Redis
    """
    try:
        await redis.flushdb()
    except RedisError as error:
        logger.warning("Could not empty Redis: %s", error)


async def clear_all_data(
    db: AsyncSession, store: ArtifactStore, redis: Redis
) -> dict:
    """
    Purge every run, job and stored file (operator wipe).

    The house agent's run folders live on this server too and go with
    them; folders on users' own machines are theirs and never touched.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param redis: The server's Redis, emptied too.
    :type redis: Redis
    :return: Summary.
    :rtype: dict
    """
    await db.execute(text(TRUNCATE_ALL))
    await db.commit()
    for folder in (UPLOADS, RUNS):
        await store.delete_folder(folder)
    shutil.rmtree(ARTIFACTS_DIR, ignore_errors=True)
    await empty_redis(redis)
    return {"status": SUCCESS, "message": WIPED_MESSAGE}


async def delete_runs(
    db: AsyncSession,
    store: ArtifactStore,
    run_ids: list[uuid.UUID],
) -> int:
    """
    Delete runs with their jobs, edges and stored files (UI files and
    zips), in one transaction. Files on the machines that ran them
    stay: they are the user's.

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
    touches_deleted = or_(
        JobDependency.upstream_id.in_(job_ids),
        JobDependency.downstream_id.in_(job_ids),
    )
    await db.execute(delete(JobDependency).where(touches_deleted))
    await db.execute(delete(Job).where(Job.id.in_(job_ids)))
    await db.execute(delete(Run).where(Run.id.in_(run_ids)))
    await db.commit()
    for run_id in run_ids:
        await store.delete_folder(run_files_folder(run_id))
    return len(job_ids)


async def delete_owned_runs(
    db: AsyncSession,
    store: ArtifactStore,
    owner_id: uuid.UUID,
    uploads: str,
    *conditions: ColumnElement[bool],
) -> int:
    """
    Delete a user's runs (all of them, or those meeting
    ``conditions``) and a folder of their uploads. Nobody else's runs
    are touched, even under the same session name.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param owner_id: The user.
    :type owner_id: uuid.UUID
    :param uploads: Their uploads folder to delete.
    :type uploads: str
    :param conditions: Which of their runs, if not all.
    :type conditions: ColumnElement[bool]
    :return: How many jobs went with the runs.
    :rtype: int
    """
    query = select(Run.id).where(Run.owner_id == owner_id, *conditions)
    run_ids = list((await db.execute(query)).scalars())
    deleted = await delete_runs(db, store, run_ids)
    await store.delete_folder(uploads)
    return deleted


async def delete_session(
    db: AsyncSession,
    store: ArtifactStore,
    session_id: str,
    user_id: uuid.UUID,
) -> dict:
    """
    Delete one of the caller's sessions: its runs, jobs and files.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param session_id: Session to delete.
    :type session_id: str
    :param user_id: The caller.
    :type user_id: uuid.UUID
    :return: Summary.
    :rtype: dict
    """
    session = sanitize_identifier(session_id)
    uploads = upload_folder(user_id, session)
    deleted = await delete_owned_runs(
        db, store, user_id, uploads, Run.session_id == session
    )
    await db.execute(
        delete(PipelineSession).where(
            PipelineSession.owner_id == user_id,
            PipelineSession.id == session,
        )
    )
    await db.commit()
    message = f"Session {session} and {deleted} jobs deleted."
    return {"status": SUCCESS, "message": message}


async def clear_user_data(
    db: AsyncSession,
    store: ArtifactStore,
    user_id: uuid.UUID,
) -> dict:
    """
    Delete all of one user's runs, jobs and stored files.

    Other users' data and the shared queue are left alone; wiping the
    whole system is an operator task (``python -m app.cli wipe``).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: The server's file store.
    :type store: ArtifactStore
    :param user_id: The caller.
    :type user_id: uuid.UUID
    :return: Summary.
    :rtype: dict
    """
    uploads = owner_uploads_folder(user_id)
    deleted = await delete_owned_runs(db, store, user_id, uploads)
    await db.execute(
        delete(PipelineSession).where(PipelineSession.owner_id == user_id)
    )
    await db.commit()
    message = f"Deleted your {deleted} jobs and their files."
    return {"status": SUCCESS, "message": message}
