"""
A run's zip ("bundle"): requested, handed to the agent that holds the
files, recorded once uploaded, removed when it expires::

    none -> requested -> packing -> ready -> expired
                                 -> too_big
                                 -> failed

Only runs on targets that bundle automatically (the house agent's) are
requested when they finish; elsewhere a user asks for one. Every move
is a conditional UPDATE, like a job's: a duplicate request or a late
report changes nothing.
"""

import uuid
from datetime import timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import BundleReport, PackRequest
from app.core.config import settings
from app.core.identifiers import sanitize_identifier
from app.models.compute_target import ComputeTarget
from app.models.job import Job
from app.models.run import Run
from app.runs.states import FINAL_STATUSES
from app.storage.keys import bundle_key
from app.storage.store import ArtifactStore

# Zipping and uploading up to a gigabyte from a cluster can take a while.
UPLOAD_LINK_SECONDS = 6 * 3600
# Packing longer than this is presumed lost; the run is requested again.
PACK_TIMEOUT = timedelta(minutes=30)


class BundleStatus(StrEnum):
    """
    Where a run's zip stands.
    """

    NONE = "none"
    REQUESTED = "requested"
    PACKING = "packing"
    READY = "ready"
    TOO_BIG = "too_big"
    FAILED = "failed"
    EXPIRED = "expired"


# A user may ask (again) for a zip from these.
REQUESTABLE = (BundleStatus.NONE, BundleStatus.FAILED, BundleStatus.EXPIRED)


def bundle_name(run: Run) -> str:
    """
    Readable name of a run's zip and its top folder.

    :param run: The run.
    :type run: Run
    :return: ``<session>_<first 8 of run id>``.
    :rtype: str
    """
    return f"{sanitize_identifier(run.session_id)}_{str(run.id)[:8]}"


async def close_run_if_finished(
    session: AsyncSession, run_id: uuid.UUID
) -> bool:
    """
    Mark the run finished if none of its jobs can change any more, and
    request its zip if its target bundles automatically.

    Call with the run's row locked (numbering the transaction's changes
    locks it): two transactions finishing the run's last two jobs then
    take turns, and the second sees the first's job as final.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :param run_id: Run whose jobs just changed.
    :type run_id: uuid.UUID
    :return: True if the run finished now.
    :rtype: bool
    """
    unfinished = exists().where(
        Job.run_id == run_id, Job.status.not_in(FINAL_STATUSES)
    )
    automatic = (
        select(ComputeTarget.bundles_automatically)
        .where(ComputeTarget.id == Run.target_id)
        .scalar_subquery()
    )
    statement = (
        update(Run)
        .where(Run.id == run_id, Run.finished_at.is_(None), ~unfinished)
        .values(
            finished_at=func.now(),
            bundle_status=case(
                (automatic, BundleStatus.REQUESTED), else_=Run.bundle_status
            ),
            bundle_requested_at=case(
                (automatic, func.now()), else_=Run.bundle_requested_at
            ),
        )
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def request_bundle(session: AsyncSession, run_id: uuid.UUID) -> bool:
    """
    Ask for a finished run's zip (a user's click).

    :param session: Open session; the caller commits.
    :type session: AsyncSession
    :param run_id: The run.
    :type run_id: uuid.UUID
    :return: True if requested now; False if the run is unfinished or
        a zip is already requested, being made, ready or too big.
    :rtype: bool
    """
    statement = (
        update(Run)
        .where(
            Run.id == run_id,
            Run.finished_at.is_not(None),
            Run.bundle_status.in_(REQUESTABLE),
        )
        .values(
            bundle_status=BundleStatus.REQUESTED,
            bundle_requested_at=func.now(),
            bundle_error=None,
        )
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def build_manifest(session: AsyncSession, run: Run) -> dict[str, Any]:
    """
    Describe a run for its zip's run.json, including jobs that never
    ran (they have no folder on the agent's machine).

    :param session: Open session.
    :type session: AsyncSession
    :param run: The run.
    :type run: Run
    :return: JSON-ready description.
    :rtype: dict[str, Any]
    """
    query = select(Job).where(Job.run_id == run.id).order_by(Job.node_key)
    jobs = (await session.execute(query)).scalars()
    return {
        "run_id": str(run.id),
        "session": run.session_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "jobs": [
            {
                "node": job.node_key,
                "task": job.script_name,
                "status": job.status,
                "attempt": job.attempt,
                "parameters": job.parameters,
                "error_message": job.error_message,
                "execution_time_seconds": job.execution_time_seconds,
                "files": job.output_files or [],
            }
            for job in jobs
        ],
    }


async def take_pack_requests(
    session: AsyncSession,
    store: ArtifactStore,
    target_id: uuid.UUID,
) -> list[PackRequest]:
    """
    Hand a target's requested zips to its agent, each once (the status
    moves to packing in the same statement that finds them).

    :param session: Open session; the caller commits.
    :type session: AsyncSession
    :param store: Signs the upload links.
    :type store: ArtifactStore
    :param target_id: The calling agent's target.
    :type target_id: uuid.UUID
    :return: One request per run to pack.
    :rtype: list[PackRequest]
    """
    statement = (
        update(Run)
        .where(
            Run.target_id == target_id,
            Run.bundle_status == BundleStatus.REQUESTED,
        )
        .values(
            bundle_status=BundleStatus.PACKING, bundle_requested_at=func.now()
        )
        .returning(Run)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    runs = list((await session.execute(statement)).scalars())
    return [
        PackRequest(
            run_id=run.id,
            bundle_name=bundle_name(run),
            upload_url=store.upload_link(
                bundle_key(run.id),
                settings.BUNDLE_MAX_BYTES,
                UPLOAD_LINK_SECONDS,
            ),
            max_bytes=settings.BUNDLE_MAX_BYTES,
            manifest=await build_manifest(session, run),
        )
        for run in runs
    ]


async def record_bundle(
    session: AsyncSession,
    target_id: uuid.UUID,
    run_id: uuid.UUID,
    report: BundleReport,
) -> bool:
    """
    Record how packing ended, if this target was packing the run.

    :param session: Open session; the caller commits.
    :type session: AsyncSession
    :param target_id: The reporting agent's target.
    :type target_id: uuid.UUID
    :param run_id: The run.
    :type run_id: uuid.UUID
    :param report: The outcome.
    :type report: BundleReport
    :return: False if the run was not being packed by this target.
    :rtype: bool
    """
    keep = timedelta(days=settings.BUNDLE_KEEP_DAYS)
    expires = func.now() + keep if report.status == BundleStatus.READY else None
    statement = (
        update(Run)
        .where(
            Run.id == run_id,
            Run.target_id == target_id,
            Run.bundle_status == BundleStatus.PACKING,
        )
        .values(
            bundle_status=report.status,
            bundle_size=report.size_bytes,
            bundle_error=report.error,
            bundle_expires_at=expires,
        )
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def expire_bundles(session: AsyncSession) -> list[uuid.UUID]:
    """
    Mark zips past their keep time as expired. The caller deletes the
    files after committing: a crash in between leaves a stray file,
    never a "ready" zip that is gone.

    :param session: Open session; the caller commits.
    :type session: AsyncSession
    :return: Runs whose zips expired.
    :rtype: list[uuid.UUID]
    """
    statement = (
        update(Run)
        .where(
            Run.bundle_status == BundleStatus.READY,
            Run.bundle_expires_at < func.now(),
        )
        .values(bundle_status=BundleStatus.EXPIRED)
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    return list((await session.execute(statement)).scalars())


async def requeue_stuck_packs(session: AsyncSession) -> int:
    """
    Request again the zips whose packing went silent (the agent died
    or restarted mid-way).

    :param session: Open session; the caller commits.
    :type session: AsyncSession
    :return: How many were requested again.
    :rtype: int
    """
    statement = (
        update(Run)
        .where(
            Run.bundle_status == BundleStatus.PACKING,
            Run.bundle_requested_at < func.now() - PACK_TIMEOUT,
        )
        .values(
            bundle_status=BundleStatus.REQUESTED, bundle_requested_at=func.now()
        )
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.execute(statement)).all())
