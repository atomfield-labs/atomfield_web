"""
A person's pipelines, kept on the server: they follow the person to any
computer, and nobody else sees them, even on the same browser.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable
from typing import Any

from sqlalchemy import Row, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import not_found
from app.models.job import Job
from app.models.pipeline_session import PipelineSession
from app.models.run import Run
from app.runs.states import JobStatus
from app.schemas.sessions import SessionDetail, SessionState, SessionSummary

SESSION_KIND = "Session"
# How a pipeline with no run yet stands.
DRAFT = SessionState.DRAFT
NOT_STARTED = {JobStatus.WAITING, JobStatus.QUEUED, JobStatus.RUNNING}
FAILED = {JobStatus.FAILED, JobStatus.UPSTREAM_FAILED}
# What the sessions page lists: everything but the draft, which can be
# large and is read only when the pipeline is opened.
LISTED = (
    PipelineSession.id,
    PipelineSession.title,
    PipelineSession.node_count,
    PipelineSession.run_id,
    PipelineSession.updated_at,
)


def run_state(jobs: Collection[tuple[str, bool]]) -> SessionState:
    """
    How a run stands: running while a job really is, waiting while jobs
    remain with none working, and afterwards how it ended. A job handed
    to a cluster counts as running only once it has started there.

    :param jobs: Each job's status, and whether it has started.
    :type jobs: Collection[tuple[str, bool]]
    :return: The state; a pipeline with no jobs is a draft.
    :rtype: SessionState
    """
    if not jobs:
        return SessionState.DRAFT
    if any(status == JobStatus.RUNNING and went for status, went in jobs):
        return SessionState.RUNNING
    statuses = {status for status, _ in jobs}
    if statuses & NOT_STARTED:
        return SessionState.WAITING
    if statuses & FAILED:
        return SessionState.FAILED
    if JobStatus.CANCELLED in statuses:
        return SessionState.CANCELLED
    return SessionState.DONE


async def run_states(
    db: AsyncSession, run_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, SessionState]:
    """
    How each of these runs stands.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param run_ids: The runs; None (no run yet) is skipped.
    :type run_ids: Iterable[uuid.UUID | None]
    :return: Run id -> state; a run with no jobs is absent.
    :rtype: dict[uuid.UUID, SessionState]
    """
    wanted = [run_id for run_id in run_ids if run_id is not None]
    query = select(Job.run_id, Job.status, Job.started_at.is_not(None)).where(
        Job.run_id.in_(wanted)
    )
    jobs: defaultdict[uuid.UUID, list[tuple[str, bool]]] = defaultdict(list)
    for run_id, status, started in await db.execute(query):
        jobs[run_id].append((status, started))
    return {run_id: run_state(found) for run_id, found in jobs.items()}


def listed_session(row: Row, state: SessionState) -> SessionSummary:
    """
    One row of the ``LISTED`` columns, as the sessions page shows it.

    :param row: The row.
    :type row: Row
    :param state: How the pipeline stands.
    :type state: SessionState
    :return: The summary.
    :rtype: SessionSummary
    """
    return SessionSummary(
        id=row.id,
        title=row.title,
        state=state,
        node_count=row.node_count,
        updated_at=row.updated_at,
    )


async def sessions_of(
    db: AsyncSession, owner_id: uuid.UUID
) -> list[SessionSummary]:
    """
    A person's pipelines, last changed first.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The person.
    :type owner_id: uuid.UUID
    :return: Their pipelines.
    :rtype: list[SessionSummary]
    """
    query = (
        select(*LISTED)
        .where(PipelineSession.owner_id == owner_id)
        .order_by(PipelineSession.updated_at.desc())
    )
    rows = (await db.execute(query)).all()
    states = await run_states(db, (row.run_id for row in rows))
    return [listed_session(row, states.get(row.run_id, DRAFT)) for row in rows]


async def session_of(
    db: AsyncSession, owner_id: uuid.UUID, session_id: str
) -> SessionDetail:
    """
    One of a person's pipelines, draft included.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The person.
    :type owner_id: uuid.UUID
    :param session_id: The pipeline.
    :type session_id: str
    :return: The pipeline.
    :rtype: SessionDetail
    :raises HTTPException: 404 if they have none with this id.
    """
    session = await db.get(PipelineSession, (owner_id, session_id))
    if session is None:
        raise not_found(SESSION_KIND, session_id)
    states = await run_states(db, [session.run_id])
    return SessionDetail(
        id=session.id,
        title=session.title,
        state=states.get(session.run_id, DRAFT),
        node_count=session.node_count,
        updated_at=session.updated_at,
        blueprint=session.blueprint,
        run_id=session.run_id,
        job_ids=session.job_ids,
    )


async def save_session(
    db: AsyncSession,
    owner_id: uuid.UUID,
    session_id: str,
    changes: dict[str, Any],
) -> None:
    """
    Change a person's pipeline, making it if it is new. One statement
    (an upsert), so two saves at once still make one pipeline.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The person.
    :type owner_id: uuid.UUID
    :param session_id: The pipeline.
    :type session_id: str
    :param changes: The columns to change; the rest stay.
    :type changes: dict[str, Any]
    """
    made = insert(PipelineSession).values(
        owner_id=owner_id, id=session_id, **changes
    )
    keys = [PipelineSession.owner_id, PipelineSession.id]
    changed = {**changes, "updated_at": func.now()}
    await db.execute(
        made.on_conflict_do_update(index_elements=keys, set_=changed)
    )


async def record_run(db: AsyncSession, run: Run, jobs: dict[str, Job]) -> None:
    """
    Note a pipeline's newest run on its session, making the session if
    a script is the first to mention it.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param run: The run.
    :type run: Run
    :param jobs: Node id -> stored job.
    :type jobs: dict[str, Job]
    """
    changes = {
        "run_id": run.id,
        "job_ids": {node: str(job.id) for node, job in jobs.items()},
        "node_count": len(jobs),
    }
    await save_session(db, run.owner_id, run.session_id, changes)
