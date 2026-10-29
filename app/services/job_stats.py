"""
Counting jobs by kind of state, for a user's statistics and the
administrator's: one grouped query each, whatever the number of jobs.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.runs.states import FAILURE_STATUSES, NOT_STARTED_STATUSES, JobStatus
from app.schemas.auth import JobCounts

# Per status: how many jobs, and the compute time they used.
PER_STATUS = (
    Job.status,
    func.count(Job.id),
    func.coalesce(func.sum(Job.execution_time_seconds), 0.0),
)


def among(by_status: Mapping[str, int], statuses: Iterable[str]) -> int:
    """
    How many jobs are in any of some states.

    :param by_status: Jobs per status.
    :type by_status: Mapping[str, int]
    :param statuses: The states counted.
    :type statuses: Iterable[str]
    :return: Their total.
    :rtype: int
    """
    return sum(by_status.get(status, 0) for status in statuses)


def tally(rows: Sequence[Sequence]) -> JobCounts:
    """
    Group per-status rows into the kinds of state people see.

    :param rows: (status, jobs, compute seconds) rows; read twice, so a
        list, not a one-pass iterator.
    :type rows: Sequence[Sequence]
    :return: The counts.
    :rtype: JobCounts
    """
    by_status = {status: jobs for status, jobs, _ in rows}
    seconds = sum(compute for _, _, compute in rows)
    return JobCounts(
        total_jobs=sum(by_status.values()),
        success_jobs=by_status.get(JobStatus.SUCCEEDED, 0),
        failed_jobs=among(by_status, FAILURE_STATUSES),
        running_jobs=by_status.get(JobStatus.RUNNING, 0),
        pending_jobs=among(by_status, NOT_STARTED_STATUSES),
        total_compute_seconds=float(seconds),
    )


async def job_counts(
    db: AsyncSession, *conditions: ColumnElement[bool]
) -> JobCounts:
    """
    Counts over the jobs meeting ``conditions`` (every job if none).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param conditions: Which jobs, e.g. one owner's.
    :type conditions: ColumnElement[bool]
    :return: The counts.
    :rtype: JobCounts
    """
    query = select(*PER_STATUS).where(*conditions).group_by(Job.status)
    return tally((await db.execute(query)).all())


async def job_counts_by_owner(db: AsyncSession) -> dict[uuid.UUID, JobCounts]:
    """
    Counts per owning key, in one query.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Owner's key id -> counts; keys without jobs are absent.
    :rtype: dict[uuid.UUID, JobCounts]
    """
    query = (
        select(Job.owner_id, *PER_STATUS)
        .where(Job.owner_id.is_not(None))
        .group_by(Job.owner_id, Job.status)
    )
    rows_by_owner: dict[uuid.UUID, list[Sequence]] = defaultdict(list)
    for owner, *per_status in (await db.execute(query)).all():
        rows_by_owner[owner].append(per_status)
    return {owner: tally(rows) for owner, rows in rows_by_owner.items()}
