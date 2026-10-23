"""
HTTP routes for runs: cancel a job or a run, and watch a run live.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_api_key,
    get_event_bus,
    get_owned_job,
    is_admin_key,
)
from app.db.session import AsyncSessionLocal, get_db
from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.events.stream import RunStream
from app.models.api_key import ApiKey
from app.models.job import Job
from app.models.run import Run
from app.runs.lifecycle import request_cancel
from app.runs.states import FINAL_STATUSES, JobStatus
from app.schemas.runs import JobCancelResponse, RunCancelResponse

router = APIRouter(tags=["Runs"])
# Stop proxies from caching the stream or holding frames back.
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
# What a cancel request did, as shown to the caller.
CANCEL_RESULTS = {
    JobStatus.CANCELLED: "cancelled",
    JobStatus.RUNNING: "cancelling",
}


async def get_owned_run(
    run_id: uuid.UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Run:
    """
    Load a run the caller may act on: their own, or any for the admin.

    :param run_id: Run id from the URL path.
    :type run_id: uuid.UUID
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The run.
    :rtype: Run
    :raises HTTPException: 404 if missing or owned by someone else.
    """
    run = await db.get(Run, run_id)
    if run is None or not (run.owner_id == api_key.id or is_admin_key(api_key)):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Run {run_id} not found"
        )
    return run


@router.post("/jobs/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job: Job = Depends(get_owned_job),
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> JobCancelResponse:
    """
    Cancel one job; a running job stops at its agent's next heartbeat.

    :param job: Job the caller owns.
    :type job: Job
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param bus: Where the changes are announced.
    :type bus: EventBus
    :return: Whether it was cancelled now or is being cancelled.
    :rtype: JobCancelResponse
    :raises HTTPException: 409 if the job has already finished.
    """
    result = await request_cancel(db, job.id)
    await commit_and_publish(db, bus)
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job already finished")
    return JobCancelResponse(job_id=job.id, status=CANCEL_RESULTS[result])


@router.post("/runs/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(
    run: Run = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> RunCancelResponse:
    """
    Cancel every unfinished job of a run.

    :param run: Run the caller owns.
    :type run: Run
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param bus: Where the changes are announced.
    :type bus: EventBus
    :return: How many were cancelled now and how many are stopping.
    :rtype: RunCancelResponse
    """
    query = select(Job.id).where(
        Job.run_id == run.id, Job.status.not_in(FINAL_STATUSES)
    )
    job_ids = list((await db.execute(query)).scalars())
    results = [await request_cancel(db, job_id) for job_id in job_ids]
    await commit_and_publish(db, bus)
    return RunCancelResponse(
        run_id=run.id,
        cancelled=results.count(JobStatus.CANCELLED),
        cancelling=results.count(JobStatus.RUNNING),
    )


@router.get("/runs/{run_id}/events", response_class=StreamingResponse)
async def watch_run(
    run: Run = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> StreamingResponse:
    """
    Stream a run's job changes as server-sent events: a snapshot first,
    then each change, with a ping every 15 seconds.

    :param run: Run the caller owns.
    :type run: Run
    :param db: The request's session, used only to check the caller.
    :type db: AsyncSession
    :param bus: Where job events arrive.
    :type bus: EventBus
    :return: A response that lasts until the browser disconnects.
    :rtype: StreamingResponse
    """
    # Checking the key left a connection checked out on this session.
    # A stream can last hours, so give it back now; the stream borrows
    # short sessions of its own.
    await db.close()
    stream = RunStream(run.id, AsyncSessionLocal, bus)
    return StreamingResponse(
        stream.frames(),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
