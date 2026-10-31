"""
What the agent API does: hand out jobs, keep leases alive, record
results. Routes stay thin; this module holds the rules.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, func, select, tuple_, update
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
    ReleaseRef,
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
from app.queue.job_queue import QueuedJob, RedisJobQueue
from app.releases.catalogs import ReleaseCatalogs
from app.releases.data_packs import data_refs, missing_data_packs
from app.releases.service import NoBuildError, release_ref
from app.runs.bundles import record_bundle, take_pack_requests
from app.runs.lifecycle import (
    Completion,
    complete_attempt,
    dispatch,
    mark_started,
    start_attempt,
)
from app.runs.states import JobStatus
from app.runs.transitions import held_by
from app.storage.keys import job_file_key, upload_folder
from app.storage.store import ArtifactStore

MISSING_TASK_MESSAGE = "Task {task!r} is no longer in the catalog"
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


# Asks whether the agent waiting for a job has hung up.
HungUp = Callable[[], Awaitable[bool]]


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


@dataclass(frozen=True, slots=True)
class JobNeeds:
    """
    What a job must have to start.

    :param task: Its catalog task.
    :type task: TaskDefinition
    :param data: The data packs it reads.
    :type data: list[DataRef]
    :param release: The file it runs from; None without a release.
    :type release: ReleaseRef | None
    """

    task: TaskDefinition
    data: list[DataRef]
    release: ReleaseRef | None


async def build_assignment(
    db: AsyncSession,
    store: ArtifactStore,
    job: Job,
    needs: JobNeeds,
) -> JobAssignment:
    """
    Describe one started attempt for the agent.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Signs the links to the job's input files.
    :type store: ArtifactStore
    :param job: The job.
    :type job: Job
    :param needs: Its task, data packs and scripts.
    :type needs: JobNeeds
    :return: The assignment, naming the file of scripts it runs.
    :rtype: JobAssignment
    """
    run = await db.get(Run, job.run_id)
    return JobAssignment(
        job_id=job.id,
        attempt=job.attempt,
        run_id=job.run_id,
        node_key=job.node_key,
        parents=await parent_keys(db, job.id),
        task=needs.task,
        parameters=job.parameters or {},
        release=needs.release,
        data=needs.data,
        deadline_at=job.deadline_at,
        **await input_fields(store, run, job),
    )


async def input_fields(
    store: ArtifactStore, run: Run, job: Job
) -> dict[str, Any]:
    """
    The files a job's folder starts with: those it declares, and a
    link to every file it gets.

    :param store: Where uploads are kept.
    :type store: ArtifactStore
    :param run: The job's run.
    :type run: Run
    :param job: The job.
    :type job: Job
    :return: ``input_files`` and ``inputs`` of its assignment.
    :rtype: dict[str, Any]
    """
    input_files = job.input_files or {}
    links = await input_links(store, run, input_files)
    return {"input_files": input_files, "inputs": links}


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
    task = await release_task(
        db, services.catalogs, run.release_id, job.script_name
    )
    if task is None:
        message = MISSING_TASK_MESSAGE.format(task=job.script_name)
        await fail_before_start(db, services, job, message)
    return task


async def release_task(
    db: AsyncSession,
    catalogs: ReleaseCatalogs,
    release_id: uuid.UUID | None,
    task_id: str,
) -> TaskDefinition | None:
    """
    A task as a release's catalog defines it (a run keeps the release
    it was submitted with, however many came since).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param catalogs: Catalogs per release.
    :type catalogs: ReleaseCatalogs
    :param release_id: The run's release; None before the first one.
    :type release_id: uuid.UUID | None
    :param task_id: The task.
    :type task_id: str
    :return: Its definition, or None if that catalog lacks it.
    :rtype: TaskDefinition | None
    """
    catalog = await catalogs.of_release(db, release_id)
    try:
        return catalog.get(task_id)
    except UnknownTaskError:
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


async def gather_needs(
    db: AsyncSession,
    services: AgentServices,
    job: Job,
    machine: str | None,
) -> JobNeeds | None:
    """
    What a queued job needs to start. Anything it cannot have fails it.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :param job: A queued job.
    :type job: Job
    :param machine: The kind of computer the agent runs on.
    :type machine: str | None
    :return: Its needs, or None if the job was failed instead.
    :rtype: JobNeeds | None
    """
    task = await find_task(db, services, job)
    data = await find_data(db, services, job, task) if task else None
    if task is None or data is None:
        return None
    run = await db.get(Run, job.run_id)
    catalog = await services.catalogs.of_release(db, run.release_id)
    package = catalog.workflow_of(job.script_name)
    store = services.store
    try:
        release = await release_ref(db, store, run.release_id, package, machine)
    except NoBuildError as error:
        await fail_before_start(db, services, job, str(error))
        return None
    return JobNeeds(task, data, release)


async def try_start(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    job_id: uuid.UUID,
    scheduled: bool = False,
    machine: str | None = None,
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
    :param machine: The kind of computer the agent runs on.
    :type machine: str | None
    :return: The assignment, or None if this message was stale.
    :rtype: JobAssignment | None
    """
    job = await db.get(Job, job_id)
    if job is None or job.status != JobStatus.QUEUED:
        return None
    needs = await gather_needs(db, services, job, machine)
    if needs is None:
        return None
    walltime = needs.task.resources.walltime_minutes
    started = await start_attempt(
        db, job_id, walltime, agent_id=target.id, scheduled=scheduled
    )
    await commit_and_publish(db, services.bus)
    if started is None:
        return None
    return await build_assignment(db, services.store, started, needs)


async def never_hung_up() -> bool:
    """
    For callers with no connection to watch: the agent is always there.

    :return: False.
    :rtype: bool
    """
    return False


async def claim_next(
    db: AsyncSession,
    services: AgentServices,
    target: ComputeTarget,
    wait_seconds: float,
    scheduled: bool = False,
    machine: str | None = None,
    hung_up: HungUp = never_hung_up,
) -> JobAssignment | None:
    """
    Hold the request open until a job arrives or the wait runs out.
    A job that arrives after the agent stopped waiting (its connection
    closed) goes back to its place in line instead of being started:
    otherwise it would sit "running" for nobody until its lease ran
    out.

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
    :param machine: The kind of computer the agent runs on.
    :type machine: str | None
    :param hung_up: Asks whether the agent stopped waiting.
    :type hung_up: HungUp
    :return: An assignment, or None if nothing arrived in time.
    :rtype: JobAssignment | None
    """
    await touch_target(db, target)
    await db.commit()
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + wait_seconds
    while (remaining := give_up_at - loop.time()) > 0:
        taken = await take_for_agent(services.queue, target, remaining, hung_up)
        if taken is None:
            return None
        assignment = await try_start(
            db, services, target, taken.job_id, scheduled, machine
        )
        if assignment is not None:
            return assignment
    return None


async def take_for_agent(
    queue: RedisJobQueue,
    target: ComputeTarget,
    wait_seconds: float,
    hung_up: HungUp,
) -> QueuedJob | None:
    """
    Take the next job for an agent that still waits for one; a job
    taken after the agent hung up goes back to its place in line.

    :param queue: Job queue.
    :type queue: RedisJobQueue
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param wait_seconds: Longest time to wait for a job.
    :type wait_seconds: float
    :param hung_up: Asks whether the agent stopped waiting.
    :type hung_up: HungUp
    :return: The job, or None if none came in time or the agent left.
    :rtype: QueuedJob | None
    """
    taken = await queue.take(target.id, wait_seconds)
    if taken is None or not await hung_up():
        return taken
    await queue.put_back(target.id, taken)
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
    renewed = await renew_leases(db, target, reports)
    await start_clocks(db, services.catalogs, target, started)
    packs = await take_pack_requests(db, services.store, target.id)
    await commit_and_publish(db, services.bus)
    return heartbeat_reply(renewed, reports, packs)


async def renew_leases(
    db: AsyncSession,
    target: ComputeTarget,
    reports: list[JobReference],
) -> list[Row]:
    """
    Renew the lease of each reported attempt that still runs on this
    agent.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param reports: Attempts the agent says it is running.
    :type reports: list[JobReference]
    :return: Each renewed attempt: job id, attempt, pending cancel.
    :rtype: list[Row]
    """
    held = [(report.job_id, report.attempt) for report in reports]
    if not held:
        return []
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
    return list((await db.execute(statement)).all())


def heartbeat_reply(
    renewed: list[Row],
    reports: list[JobReference],
    packs: list[PackRequest],
) -> HeartbeatResponse:
    """
    What the agent must do: cancel the renewed attempts whose job got
    a cancel request, abandon those no longer its own, zip these runs.

    :param renewed: Renewed attempts: job id, attempt, pending cancel.
    :type renewed: list[Row]
    :param reports: Attempts the agent says it is running.
    :type reports: list[JobReference]
    :param packs: Runs to zip.
    :type packs: list[PackRequest]
    :return: The reply.
    :rtype: HeartbeatResponse
    """
    alive = {(row.id, row.attempt) for row in renewed}
    cancel = [
        JobReference(job_id=row.id, attempt=row.attempt)
        for row in renewed
        if row.cancel_requested
    ]
    abandon = [
        report
        for report in reports
        if (report.job_id, report.attempt) not in alive
    ]
    return HeartbeatResponse(pack=packs, cancel=cancel, abandon=abandon)


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
    completion = await apply_report(db, target, job_id, report)
    if completion and report.folder:
        await record_folder(db, completion.job.run_id, report)
    await commit_and_publish(db, services.bus)
    if completion:
        await dispatch(db, services.queue, completion.ready)
    return completion


async def apply_report(
    db: AsyncSession,
    target: ComputeTarget,
    job_id: uuid.UUID,
    report: CompletionRequest,
) -> Completion | None:
    """
    Finish an attempt as its agent reports it, if that agent's attempt
    still holds the job; only the outcome's own fields are recorded.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: Finished job.
    :type job_id: uuid.UUID
    :param report: How the attempt ended.
    :type report: CompletionRequest
    :return: The completion, or None for a stale report.
    :rtype: Completion | None
    """
    fields = OUTCOME_FIELDS[report.outcome]
    values = {name: getattr(report, name) for name in fields}
    return await complete_attempt(
        db,
        job_id,
        report.outcome,
        expected_attempt=report.attempt,
        expected_agent=target.id,
        output_files=[card.model_dump() for card in report.files],
        **values,
    )


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
    run_id = await attempt_run(db, target, job_id, request.attempt)
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


async def attempt_run(
    db: AsyncSession,
    target: ComputeTarget,
    job_id: uuid.UUID,
    attempt: int,
) -> uuid.UUID | None:
    """
    The run of an attempt that still holds its job on this agent.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param job_id: The job.
    :type job_id: uuid.UUID
    :param attempt: The attempt.
    :type attempt: int
    :return: The run's id, or None if the attempt is stale.
    :rtype: uuid.UUID | None
    """
    query = select(Job.run_id).where(*held_by(job_id, attempt, target.id))
    return (await db.execute(query)).scalar_one_or_none()


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
    waiting = await clocks_to_start(db, started)
    for reference in started:
        row = waiting.get(reference.job_id)
        task = row and await release_task(
            db, catalogs, row.release_id, row.script_name
        )
        if task:
            await mark_started(
                db,
                reference.job_id,
                reference.attempt,
                target.id,
                task.resources.walltime_minutes,
            )


async def clocks_to_start(
    db: AsyncSession, started: list[JobReference]
) -> dict[uuid.UUID, Row]:
    """
    Of the jobs reported running, those whose clock has not started.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param started: Attempts reported running.
    :type started: list[JobReference]
    :return: Job id -> its task name and run's release.
    :rtype: dict[uuid.UUID, Row]
    """
    if not started:
        return {}
    query = (
        select(Job.id, Job.script_name, Run.release_id)
        .join(Run, Run.id == Job.run_id)
        .where(
            Job.id.in_([reference.job_id for reference in started]),
            Job.started_at.is_(None),
        )
    )
    return {row.id: row for row in (await db.execute(query)).all()}
