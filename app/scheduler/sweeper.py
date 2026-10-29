"""
The sweeper: a loop that repairs whatever the happy path missed.

Every pass it:

1. re-adds every queued job to its target's Redis queue (a message lost
   to a crash between commit and dispatch, or to a Redis restart);
2. handles running jobs whose agent went silent: cancels them if a
   cancel is pending, retries them if attempts remain, else fails them;
3. fails running jobs long past their deadline.

Each repair is a conditional update in its own transaction, re-checking
its condition, so the sweeper can never undo progress an agent made a
moment earlier. Repairs are announced like any other job change.
Only one API process sweeps per interval: each pass first takes a
short Redis lock.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import ColumnElement, Row, Select, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.models.job import Job
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.runs.bundles import expire_bundles, requeue_stuck_packs
from app.runs.lifecycle import (
    SilenceLimits,
    complete_attempt,
    lease_expired,
    requeue_lost,
)
from app.runs.states import JobStatus
from app.storage.keys import bundle_key
from app.storage.store import ArtifactStore

logger = logging.getLogger(__name__)
LOCK_KEY = "sweeper:lock"
LOST_CANCELLED_MESSAGE = "Cancelled; its agent stopped responding"
LOST_FAILED_MESSAGE = (
    "Its agent stopped responding; gave up after {attempts} attempts"
)
OVERDUE_MESSAGE = "Ran past its time limit"


def lost_reason(outcome: JobStatus, attempt: int) -> str:
    """
    Why a job whose agent went silent was ended.

    :param outcome: CANCELLED (a cancel was pending) or FAILED.
    :type outcome: JobStatus
    :param attempt: The attempt that was lost (also how many ran).
    :type attempt: int
    :return: The message shown on the job.
    :rtype: str
    """
    if outcome is JobStatus.CANCELLED:
        return LOST_CANCELLED_MESSAGE
    return LOST_FAILED_MESSAGE.format(attempts=attempt)


@dataclass(slots=True)
class SweepReport:
    """
    What one pass repaired.
    """

    resent: int = 0
    retried: int = 0
    cancelled: int = 0
    failed: int = 0
    overdue: int = 0
    expired: int = 0
    repacked: int = 0

    @property
    def changed_anything(self) -> bool:
        """
        Whether this pass repaired anything worth logging.

        :return: True if any count is non-zero.
        :rtype: bool
        """
        counts = (
            self.retried,
            self.cancelled,
            self.failed,
            self.overdue,
            self.expired,
            self.repacked,
        )
        return any(counts)


class Sweeper:
    """
    Periodically repairs queue and lease state.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        queue: RedisJobQueue,
        bus: EventBus,
        redis: Redis,
        store: ArtifactStore,
        interval_seconds: float,
        limits: SilenceLimits,
        deadline_grace: timedelta,
    ) -> None:
        """
        Configure the sweeper.

        :param session_factory: Creates database sessions.
        :type session_factory: async_sessionmaker
        :param queue: Job queue to refill.
        :type queue: RedisJobQueue
        :param bus: Where repairs are announced.
        :type bus: EventBus
        :param redis: Redis client for the round lock.
        :type redis: Redis
        :param store: Where expired zips are deleted from.
        :type store: ArtifactStore
        :param interval_seconds: Time between passes.
        :type interval_seconds: float
        :param limits: Silence after which a job counts as lost, by
            kind of job (local, scheduled).
        :type limits: SilenceLimits
        :param deadline_grace: Extra time past a deadline before failing.
        :type deadline_grace: timedelta
        """
        self.session_factory = session_factory
        self.queue = queue
        self.bus = bus
        self.redis = redis
        self.store = store
        self.interval_seconds = interval_seconds
        self.limits = limits
        self.deadline_grace = deadline_grace

    async def run_forever(self) -> None:
        """
        Sweep every interval until cancelled.

        A failed pass is logged and the loop goes on: the sweeper is the
        repair mechanism, so dying on a database blip would be worse
        than the blip itself.
        """
        while True:
            try:
                if await self.acquire_round():
                    report = await self.sweep_once()
                    if report.changed_anything:
                        logger.info("Sweeper repaired: %s", report)
            except Exception:
                logger.exception("Sweep pass failed; retrying next interval")
            await asyncio.sleep(self.interval_seconds)

    async def acquire_round(self) -> bool:
        """
        Take this interval's lock; only one process sweeps per round.

        The lock expires before the next round, so if the holder dies
        another process simply takes the next one.

        :return: True if this process should sweep now.
        :rtype: bool
        """
        seconds = max(1, int(self.interval_seconds) - 1)
        return bool(await self.redis.set(LOCK_KEY, "1", nx=True, ex=seconds))

    async def sweep_once(self) -> SweepReport:
        """
        Run every repair once.

        :return: Counts of what was repaired.
        :rtype: SweepReport
        """
        report = SweepReport()
        report.resent = await self.resend_queued()
        await self.handle_lost_leases(report)
        report.overdue = await self.fail_overdue()
        report.expired = await self.delete_expired_bundles()
        report.repacked = await self.requeue_silent_packing()
        return report

    async def delete_expired_bundles(self) -> int:
        """
        Mark zips past their keep time expired, then delete their files.

        :return: How many expired.
        :rtype: int
        """
        async with self.session_factory() as session:
            expired = await expire_bundles(session)
            await session.commit()
        for run_id in expired:
            await self.store.delete(bundle_key(run_id))
        return len(expired)

    async def requeue_silent_packing(self) -> int:
        """
        Request again the zips whose agent went quiet while packing.

        :return: How many were requested again.
        :rtype: int
        """
        async with self.session_factory() as session:
            count = await requeue_stuck_packs(session)
            await session.commit()
        return count

    async def read(self, query: Select) -> list[Row]:
        """
        The rows of a read-only query, in a session of its own.

        :param query: The query.
        :type query: Select
        :return: Its rows.
        :rtype: list[Row]
        """
        async with self.session_factory() as session:
            return list((await session.execute(query)).all())

    async def resend_queued(self) -> int:
        """
        Add every queued job to its target's queue; jobs already there
        are left alone (the queue ignores duplicates).

        :return: How many were missing from Redis.
        :rtype: int
        """
        query = (
            select(Job.id, Run.target_id)
            .join(Run, Run.id == Job.run_id)
            .where(Job.status == JobStatus.QUEUED)
        )
        return await self.queue.add_by_target(await self.read(query))

    async def handle_lost_leases(self, report: SweepReport) -> None:
        """
        Resolve every running job whose agent has gone silent: cancel it
        if a cancel is pending, retry it if attempts remain, else fail
        it.

        :param report: Pass report to update.
        :type report: SweepReport
        """
        query = (
            select(
                Job.id,
                Job.attempt,
                Job.max_attempts,
                Job.cancel_requested,
                Run.target_id,
            )
            .join(Run, Run.id == Job.run_id)
            .where(Job.status == JobStatus.RUNNING, lease_expired(self.limits))
        )
        for lost in await self.read(query):
            await self.resolve_lost(lost, report)

    async def resolve_lost(self, lost: Row, report: SweepReport) -> None:
        """
        Cancel, retry or fail one job whose agent went silent.

        :param lost: The job's id, attempt, attempts allowed, pending
            cancel and run target.
        :type lost: Row
        :param report: Pass report to update.
        :type report: SweepReport
        """
        if lost.cancel_requested:
            report.cancelled += await self.end_lost(
                lost.id, lost.attempt, JobStatus.CANCELLED
            )
        elif lost.attempt < lost.max_attempts:
            report.retried += await self.retry_lost(
                lost.id, lost.attempt, lost.target_id
            )
        else:
            report.failed += await self.end_lost(
                lost.id, lost.attempt, JobStatus.FAILED
            )

    async def retry_lost(
        self, job_id: uuid.UUID, attempt: int, target_id: uuid.UUID
    ) -> int:
        """
        Queue a lost job again (an infrastructure failure, not the
        task's fault), then dispatch it.

        :param job_id: Lost job.
        :type job_id: uuid.UUID
        :param attempt: Its lost attempt.
        :type attempt: int
        :param target_id: Its run's compute target.
        :type target_id: uuid.UUID
        :return: 1 if retried, 0 if it turned out not to be lost.
        :rtype: int
        """
        async with self.session_factory() as session:
            job = await requeue_lost(session, job_id, attempt, self.limits)
            await commit_and_publish(session, self.bus)
        if job is None:
            return 0
        await self.queue.add(target_id, [job_id])
        return 1

    async def end_lost(
        self, job_id: uuid.UUID, attempt: int, outcome: JobStatus
    ) -> int:
        """
        Finish a lost job as cancelled or failed, with its descendants.

        :param job_id: Lost job.
        :type job_id: uuid.UUID
        :param attempt: Its lost attempt.
        :type attempt: int
        :param outcome: CANCELLED or FAILED.
        :type outcome: JobStatus
        :return: 1 if finished, 0 if it turned out not to be lost.
        :rtype: int
        """
        reason = lost_reason(outcome, attempt)
        condition = lease_expired(self.limits)
        return await self.finish(job_id, attempt, outcome, condition, reason)

    async def finish(
        self,
        job_id: uuid.UUID,
        attempt: int,
        outcome: JobStatus,
        condition: ColumnElement[bool],
        reason: str,
    ) -> int:
        """
        End one job, in a transaction of its own, if ``condition`` still
        holds when the update runs (the agent may have just reported).

        :param job_id: The job.
        :type job_id: uuid.UUID
        :param attempt: The attempt being ended.
        :type attempt: int
        :param outcome: CANCELLED or FAILED.
        :type outcome: JobStatus
        :param condition: Why it is ended, checked again in the update.
        :type condition: ColumnElement[bool]
        :param reason: Message shown on the job.
        :type reason: str
        :return: 1 if ended, 0 if the condition no longer held.
        :rtype: int
        """
        async with self.session_factory() as session:
            done = await complete_attempt(
                session,
                job_id,
                outcome,
                expected_attempt=attempt,
                extra_conditions=[condition],
                error_message=reason,
            )
            await commit_and_publish(session, self.bus)
        return int(done is not None)

    async def fail_overdue(self) -> int:
        """
        Fail running jobs long past their deadline. Not retried: the
        same work would run out of time again.

        :return: How many were failed.
        :rtype: int
        """
        overdue = Job.deadline_at < func.now() - self.deadline_grace
        query = select(Job.id, Job.attempt).where(
            Job.status == JobStatus.RUNNING, overdue
        )
        failed = 0
        for job_id, attempt in await self.read(query):
            failed += await self.finish(
                job_id, attempt, JobStatus.FAILED, overdue, OVERDUE_MESSAGE
            )
        return failed
