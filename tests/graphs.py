"""
Helpers that store small job graphs for database-level tests.
"""

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import InMemoryEventBus
from app.events.changes import commit_and_publish
from app.events.models import JobEvent
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.runs.lifecycle import create_run
from app.runs.states import JobStatus


async def build_graph(
    session: AsyncSession,
    edges: list[tuple[str, str]],
) -> dict[str, uuid.UUID]:
    """
    Store a run whose jobs and edges follow ``edges``, as a submission
    would: roots queued, the rest waiting on their parent count.

    :param session: Open session.
    :type session: AsyncSession
    :param edges: (parent, child) name pairs.
    :type edges: list[tuple[str, str]]
    :return: Job name -> id.
    :rtype: dict[str, uuid.UUID]
    """
    run = await create_run(session, None, f"graph_{uuid.uuid4().hex[:8]}")
    parents = Counter(child for _, child in edges)
    names = sorted({name for edge in edges for name in edge})
    jobs = {
        name: Job(
            run_id=run.id,
            script_name="toy_opt",
            pending_parents=parents[name],
            status=JobStatus.WAITING if parents[name] else JobStatus.QUEUED,
        )
        for name in names
    }
    session.add_all(jobs.values())
    await session.flush()
    session.add_all(
        JobDependency(upstream_id=jobs[a].id, downstream_id=jobs[b].id)
        for a, b in edges
    )
    await session.commit()
    return {name: job.id for name, job in jobs.items()}


async def snapshot(
    session: AsyncSession,
    ids: dict[str, uuid.UUID],
) -> dict[str, tuple[str, int]]:
    """
    Read every job's status and parent count, fresh from the database.

    :param session: Open session.
    :type session: AsyncSession
    :param ids: Job name -> id.
    :type ids: dict[str, uuid.UUID]
    :return: Name -> (status, pending_parents).
    :rtype: dict[str, tuple[str, int]]
    """
    state = {}
    for name, job_id in ids.items():
        job = await session.get(Job, job_id, populate_existing=True)
        state[name] = (job.status, job.pending_parents)
    return state


async def commit_changes(session: AsyncSession) -> list[JobEvent]:
    """
    Commit job changes the way the app does (numbered, then published),
    to a bus nobody listens to.

    :param session: Session holding the changes.
    :type session: AsyncSession
    :return: The numbered events.
    :rtype: list[JobEvent]
    """
    return await commit_and_publish(session, InMemoryEventBus())


async def run_counter(session: AsyncSession, job_id: uuid.UUID) -> int:
    """
    Read the event counter of a job's run.

    :param session: Open session.
    :type session: AsyncSession
    :param job_id: Any job of the run.
    :type job_id: uuid.UUID
    :return: How many changes the run has announced.
    :rtype: int
    """
    query = (
        select(Run.event_seq)
        .join(Job, Job.run_id == Run.id)
        .where(Job.id == job_id)
    )
    return (await session.execute(query)).scalar_one()
