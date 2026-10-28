"""
What the agent API does: hand out jobs, keep leases alive, record
results. Routes stay thin; this module holds the rules.
"""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auth import touch_target
from app.agents.schemas import (
    UI_FILE_MAX_BYTES,
    BundleReport,
    CompletionRequest,
    DataRef,
    HeartbeatResponse,
    InputFile,
    JobAssignment,
    JobReference,
    PackRequest,
    UploadLinksRequest,
    UploadLinksResponse,
)
from app.catalog.catalog import UnknownTaskError
from app.catalog.models import TaskDefinition
from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.models.compute_target import ComputeTarget
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.releases.catalogs import ReleaseCatalogs
from app.releases.data_packs import data_refs, missing_data_packs
from app.releases.service import release_ref
from app.runs.bundles import record_bundle, take_pack_requests
from app.runs.lifecycle import (
    Completion,
    complete_attempt,
    mark_started,
    start_attempt,
)
from app.runs.states import JobStatus
from app.storage.keys import job_file_key, upload_folder
from app.storage.store import ArtifactStore

# Columns an outcome may record; anything else in a report is ignored.
OUTCOME_FIELDS = {
    JobStatus.SUCCEEDED: ("output_data", "execution_time_seconds"),
    JobStatus.FAILED: ("error_message", "execution_time_seconds"),
    JobStatus.CANCELLED: ("error_message", "execution_time_seconds"),
}
# Inputs are fetched right after the claim; an hour is ample.
INPUT_LINK_SECONDS = 3600
# Small files are uploaded right before the report.
UPLOAD_LINK_SECONDS = 600


@dataclass(frozen=True, slots=True)
class AgentServices:
    """
    The shared parts the agent API works with, passed as one object
    instead of one argument each.
    """

    queue: RedisJobQueue
    bus: EventBus
    catalogs: ReleaseCatalogs
    store: ArtifactStore


async def input_links(
    store: ArtifactStore,
    run: Run,
    input_files: dict[str, list[str]],
) -> list[InputFile]:
    """
    Sign a download link for every file the job's folder starts with:
    all files uploaded to the session (as scripts with an optional
    input expect), plus any declared input. A declared file that is
    missing gets a link anyway, so the job fails naming it.

    :param store: Where uploads are kept.
    :type store: ArtifactStore
    :param run: The job's run (owner and session name the uploads).
    :type run: Run
    :param input_files: Port -> declared file names.
    :type input_files: dict[str, list[str]]
    :return: One link per distinct file, by name.
    :rtype: list[InputFile]
    """
    folder = upload_folder(run.owner_id, run.session_id)
    declared = {name for names in input_files.values() for name in names}
    names = sorted(declared.union(await store.list_names(folder)))
    return [
        InputFile(
            name=name,
            url=store.download_link(f"{folder}/{name}", INPUT_LINK_SECONDS),
        )
        for name in names
    ]


async def parent_keys(db: AsyncSession, job_id: uuid.UUID) -> list[str]:
    """
    Folder names of a job's parents.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_id: The child.
    :type job_id: uuid.UUID
    :return: Parent node keys, sorted.
    :rtype: list[str]
    """
    query = (
        select(Job.node_key)
        .join(JobDependency, JobDependency.upstream_id == Job.id)
        .where(JobDependency.downstream_id == job_id)
        .order_by(Job.node_key)
    )
    return list((await db.execute(query)).scalars())


async def build_assignment(
    db: AsyncSession,
    store: ArtifactStore,
    job: Job,
    task: TaskDefinition,
    data: list[DataRef],
) -> JobAssignment:
    """
    Describe a started attempt for its agent.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the inputs are kept.
    :type store: ArtifactStore
    :param job: The job, just started.
    :type job: Job
    :param task: Its catalog task.
    :type task: TaskDefinition
    :param data: The data packs it reads.
    :type data: list[DataRef]
    :return: The assignment, naming the run's scripts release.
    :rtype: JobAssignment
    """
    run = await db.get(Run, job.run_id)
    input_files = job.input_files or {}
    return JobAssignment(
        job_id=job.id,
        attempt=job.attempt,
        run_id=job.run_id,
        node_key=job.node_key,
        parents=await parent_keys(db, job.id),
        task=task,
        parameters=job.parameters or {},
        input_files=input_files,
        inputs=await input_links(store, run, input_files),
        release=await release_ref(db, store, run.release_id),
        data=data,
        deadline_at=job.deadline_at,
    )


async def find_task(
    db: AsyncSession,
    services: AgentServices,
    job: Job,
) -> TaskDefinition | None:
    """
    A job's task, from the catalog of its run's release (not the
    newest one: a run keeps its release). A task that is not there
    fails the job.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param job: A queued job.
    :type job: Job
    :return: The task, or None if the job was failed instead.
    :rtype: TaskDefinition | None
    """
    run = await db.get(Run, job.run_id)
    catalog = await services.catalogs.of_release(db, run.release_id)
    try:
        return catalog.get(job.script_name)
    except UnknownTaskError:
        message = f"Task {job.script_name!r} is no longer in the catalog"
        await fail_before_start(db, services, job, message)
        return None


async def find_data(
    db: AsyncSession,
    services: AgentServices,
    job: Job,
    task: TaskDefinition,
) -> list[DataRef] | None:
    """
    The data packs a job's task reads, with download links. A pack
    that was never published fails the job (a release cannot name
    one, but the catalog file of runs without a release can).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param job: A queued job.
    :type job: Job
    :param task: Its task.
    :type task: TaskDefinition
    :return: The references, or None if the job was failed instead.
    :rtype: list[DataRef] | None
    """
    missing = await missing_data_packs(db, task.data)
    if missing:
        message = f"Data packs not published: {', '.join(missing)}"
        await fail_before_start(db, services, job, message)
        return None
    return await data_refs(db, services.store, task.data)


async def fail_before_start(
    db: AsyncSession,
    services: AgentServices,
    job: Job,
    message: str,
) -> None:
    """
    Fail a queued job that cannot start, and announce it.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param job: The job.
    :type job: Job
    :param message: Why it cannot start.
    :type message: str
    """
    await complete_attempt(db, job.id, JobStatus.FAILED, error_message=message)
    await commit_and_publish(db, services.bus)


async def try_start(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    job_id: uuid.UUID,
    scheduled: bool = False,
) -> JobAssignment | None:
    """
    Turn one queue message into a started attempt, if still valid.

    A message can be stale (the job was cancelled, or a duplicate was
    already claimed); then the conditional update finds nothing and the
    caller simply takes the next message.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: Job id from the queue.
    :type job_id: uuid.UUID
    :param scheduled: The agent hands jobs to a scheduler, so the job
        starts later (its clock starts when reported running).
    :type scheduled: bool
    :return: The assignment, or None if this message was stale.
    :rtype: JobAssignment | None
    """
    job = await db.get(Job, job_id)
    if job is None or job.status != JobStatus.QUEUED:
        return None
    task = await find_task(db, services, job)
    data = await find_data(db, services, job, task) if task else None
    if task is None or data is None:
        return None
    walltime = task.resources.walltime_minutes
    started = await start_attempt(
        db, job_id, walltime, agent_id=target.id, scheduled=scheduled
    )
    await commit_and_publish(db, services.bus)
    if started is None:
        return None
    return await build_assignment(db, services.store, started, task, data)


async def claim_next(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    wait_seconds: float,
    scheduled: bool = False,
) -> JobAssignment | None:
    """
    Hold the request open until a job arrives or the wait runs out.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param wait_seconds: Longest time to wait.
    :type wait_seconds: float
    :param scheduled: The agent hands jobs to a scheduler.
    :type scheduled: bool
    :return: An assignment, or None if nothing arrived in time.
    :rtype: JobAssignment | None
    """
    await touch_target(db, target)
    await db.commit()
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + wait_seconds
    while (remaining := give_up_at - loop.time()) > 0:
        job_id = await services.queue.pop(target.id, remaining)
        if job_id is None:
            return None
        assignment = await try_start(db, services, target, job_id, scheduled)
        if assignment is not None:
            return assignment
    return None


async def record_heartbeat(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    reports: list[JobReference],
    started: list[JobReference] = (),
) -> HeartbeatResponse:
    """
    Renew the leases an agent still holds, tell it what to stop, and
    hand it any runs waiting to be zipped.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param reports: Attempts the agent says it is running.
    :type reports: list[JobReference]
    :param started: Those a scheduler has begun running.
    :type started: list[JobReference]
    :return: Attempts to cancel, and attempts that are no longer its.
    :rtype: HeartbeatResponse
    """
    await touch_target(db, target)
    held = [(report.job_id, report.attempt) for report in reports]
    rows = []
    if held:
        statement = (
            update(Job)
            .where(
                Job.agent_id == target.id,
                Job.status == JobStatus.RUNNING,
                tuple_(Job.id, Job.attempt).in_(held),
            )
            .values(last_heartbeat_at=func.now())
            .returning(Job.id, Job.attempt, Job.cancel_requested)
        )
        rows = (await db.execute(statement)).all()
    await start_clocks(db, services.catalogs, target, started)
    packs = await take_pack_requests(db, services.store, target.id)
    await commit_and_publish(db, services.bus)
    alive = {(job_id, attempt) for job_id, attempt, _ in rows}
    return HeartbeatResponse(
        pack=packs,
        cancel=[
            JobReference(job_id=job_id, attempt=attempt)
            for job_id, attempt, cancel_requested in rows
            if cancel_requested
        ],
        abandon=[
            report
            for report in reports
            if (report.job_id, report.attempt) not in alive
        ],
    )


async def report_completion(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    job_id: uuid.UUID,
    report: CompletionRequest,
) -> Completion | None:
    """
    Record how an attempt ended, then queue the children it released.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: Finished job.
    :type job_id: uuid.UUID
    :param report: How the attempt ended.
    :type report: CompletionRequest
    :return: The completion, or None if this agent's attempt no longer
        owns the job (stale report).
    :rtype: Completion | None
    """
    outcome = JobStatus(report.outcome)
    values = {
        field: getattr(report, field) for field in OUTCOME_FIELDS[outcome]
    }
    files = [card.model_dump() for card in report.files]
    completion = await complete_attempt(
        db,
        job_id,
        outcome,
        expected_attempt=report.attempt,
        expected_agent=target.id,
        output_files=files,
        **values,
    )
    if completion and report.folder:
        await record_folder(db, completion.job.run_id, report)
    await commit_and_publish(db, services.bus)
    if completion and completion.ready:
        ready_ids = [child.id for child in completion.ready]
        await services.queue.add(target.id, ready_ids)
    return completion


async def record_folder(
    db: AsyncSession,
    run_id: uuid.UUID,
    report: CompletionRequest,
) -> None:
    """
    Remember where the run's folder is on the agent's machine.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param run_id: The run.
    :type run_id: uuid.UUID
    :param report: A completion that carries the folder location.
    :type report: CompletionRequest
    """
    await db.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(
            folder_path=report.folder.path,
            folder_address=report.folder.address,
        )
    )


async def upload_links(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    job_id: uuid.UUID,
    request: UploadLinksRequest,
) -> UploadLinksResponse | None:
    """
    Sign one upload link per small file of a finished attempt, if that
    attempt (on this agent) still holds the job.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: The job whose files these are.
    :type job_id: uuid.UUID
    :param request: Attempt and file names.
    :type request: UploadLinksRequest
    :return: The links, or None if the attempt no longer holds the job.
    :rtype: UploadLinksResponse | None
    :raises InvalidKeyError: If a name is not a plain file name.
    """
    query = select(Job.run_id).where(
        Job.id == job_id,
        Job.status == JobStatus.RUNNING,
        Job.attempt == request.attempt,
        Job.agent_id == target.id,
    )
    run_id = (await db.execute(query)).scalar_one_or_none()
    if run_id is None:
        return None
    links = {
        name: services.store.upload_link(
            job_file_key(run_id, job_id, name),
            UI_FILE_MAX_BYTES,
            UPLOAD_LINK_SECONDS,
        )
        for name in request.names
    }
    return UploadLinksResponse(links=links, max_bytes=UI_FILE_MAX_BYTES)


async def hand_out_packs(
    db: AsyncSession,
    store: ArtifactStore,
    target: ComputeTarget,
) -> list[PackRequest]:
    """
    Take the target's requested zips (e.g. the run a report just
    finished) so the reply can carry them without waiting for the next
    heartbeat.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Signs upload links for zips.
    :type store: ArtifactStore
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :return: Runs to zip and upload.
    :rtype: list[PackRequest]
    """
    packs = await take_pack_requests(db, store, target.id)
    await db.commit()
    return packs


async def report_bundle(
    db: AsyncSession,
    target: ComputeTarget,
    run_id: uuid.UUID,
    report: BundleReport,
) -> bool:
    """
    Record how packing a run ended.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param run_id: The run.
    :type run_id: uuid.UUID
    :param report: The outcome.
    :type report: BundleReport
    :return: False if this target was not packing the run.
    :rtype: bool
    """
    recorded = await record_bundle(db, target.id, run_id, report)
    await db.commit()
    return recorded


async def start_clocks(
    db: AsyncSession,
    catalogs: ReleaseCatalogs,
    target: ComputeTarget,
    started: list[JobReference],
) -> None:
    """
    Start the clock of each job a scheduler has begun running: its
    start time, and a deadline its task's walltime away.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param catalogs: Give each task's walltime, per release.
    :type catalogs: ReleaseCatalogs
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param started: Attempts reported running.
    :type started: list[JobReference]
    """
    if not started:
        return
    ids = [reference.job_id for reference in started]
    query = (
        select(Job.id, Job.script_name, Run.release_id)
        .join(Run, Run.id == Job.run_id)
        .where(Job.id.in_(ids), Job.started_at.is_(None))
    )
    waiting = {row.id: row for row in (await db.execute(query)).all()}
    for reference in started:
        if reference.job_id not in waiting:
            continue
        row = waiting[reference.job_id]
        walltime = await task_walltime(db, catalogs, row)
        if walltime is not None:
            await mark_started(
                db, reference.job_id, reference.attempt, target.id, walltime
            )


async def task_walltime(
    db: AsyncSession, catalogs: ReleaseCatalogs, row
) -> int | None:
    """
    A job's time limit in minutes, from its run's release.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param catalogs: Catalogs per release.
    :type catalogs: ReleaseCatalogs
    :param row: The job's id, task name and run's release.
    :type row: sqlalchemy.Row
    :return: Minutes, or None if its task is gone.
    :rtype: int | None
    """
    catalog = await catalogs.of_release(db, row.release_id)
    try:
        return catalog.get(row.script_name).resources.walltime_minutes
    except UnknownTaskError:
        return None
