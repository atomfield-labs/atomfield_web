"""
Helpers that store small job graphs for database-level tests.
"""

import uuid
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobDependency
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
