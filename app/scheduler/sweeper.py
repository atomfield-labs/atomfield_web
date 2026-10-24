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
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.models.job import Job
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from app.runs.bundles import expire_bundles, requeue_stuck_packs
from app.runs.lifecycle import complete_attempt, lease_expired, requeue_lost
from app.runs.states import JobStatus
from app.storage.keys import bundle_key
from app.storage.store import ArtifactStore

logger = logging.getLogger(__name__)
LOCK_KEY = "sweeper:lock"


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
        lease_timeout: timedelta,
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
        :param lease_timeout: Silence after which a job counts as lost.
        :type lease_timeout: timedelta
        :param deadline_grace: Extra time past a deadline before failing.
        :type deadline_grace: timedelta
        """
        self.session_factory = session_factory
        self.queue = queue
        self.bus = bus
        self.redis = redis
        self.store = store
        self.interval_seconds = interval_seconds
        self.lease_timeout = lease_timeout
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
        async with self.session_factory() as session:
            rows = (await session.execute(query)).all()
        by_target = defaultdict(list)
        for job_id, target_id in rows:
            by_target[target_id].append(job_id)
        added = 0
        for target_id, job_ids in by_target.items():
            added += await self.queue.add(target_id, job_ids)
        return added

    async def handle_lost_leases(self, report: SweepReport) -> None:
        """
        Resolve every running job whose agent has gone silent.

        :param report: Pass report to update.
        :type report: SweepReport
        """
        expired = lease_expired(self.lease_timeout)
        query = (
            select(
                Job.id,
                Job.attempt,
                Job.max_attempts,
                Job.cancel_requested,
                Run.target_id,
            )
            .join(Run, Run.id == Job.run_id)
            .where(Job.status == JobStatus.RUNNING, expired)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(query)).all()
        for job_id, attempt, max_attempts, cancel, target_id in rows:
            if cancel:
                report.cancelled += await self.end_lost(
                    job_id, attempt, JobStatus.CANCELLED
                )
            elif attempt < max_attempts:
                report.retried += await self.retry_lost(
                    job_id, attempt, target_id
                )
            else:
                report.failed += await self.end_lost(
                    job_id, attempt, JobStatus.FAILED
                )

    async def retry_lost(self, job_id, attempt: int, target_id) -> int:
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
            job = await requeue_lost(
                session, job_id, attempt, self.lease_timeout
            )
            await commit_and_publish(session, self.bus)
        if job is None:
            return 0
        await self.queue.add(target_id, [job_id])
        return 1

    async def end_lost(self, job_id, attempt: int, outcome: JobStatus) -> int:
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
        reason = {
            JobStatus.CANCELLED: "Cancelled; its agent stopped responding",
            JobStatus.FAILED: (
                f"Its agent stopped responding; gave up after "
                f"{attempt} attempts"
            ),
        }[outcome]
        async with self.session_factory() as session:
            done = await complete_attempt(
                session,
                job_id,
                outcome,
                expected_attempt=attempt,
                extra_conditions=[lease_expired(self.lease_timeout)],
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
        async with self.session_factory() as session:
            rows = (await session.execute(query)).all()
            failed = 0
            for job_id, attempt in rows:
                done = await complete_attempt(
                    session,
                    job_id,
                    JobStatus.FAILED,
                    expected_attempt=attempt,
                    extra_conditions=[overdue],
                    error_message="Ran past its time limit",
                )
                await commit_and_publish(session, self.bus)
                failed += int(done is not None)
        return failed
