"""
HTTP routes for cancelling jobs and runs.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_api_key,
    get_owned_job,
    is_admin_key,
)
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.job import Job
from app.models.run import Run
from app.runs.lifecycle import request_cancel
from app.runs.states import FINAL_STATUSES, JobStatus
from app.schemas.runs import JobCancelResponse, RunCancelResponse

router = APIRouter(tags=["Cancellation"])
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
) -> JobCancelResponse:
    """
    Cancel one job; a running job stops at its agent's next heartbeat.

    :param job: Job the caller owns.
    :type job: Job
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Whether it was cancelled now or is being cancelled.
    :rtype: JobCancelResponse
    :raises HTTPException: 409 if the job has already finished.
    """
    result = await request_cancel(db, job.id)
    await db.commit()
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job already finished")
    return JobCancelResponse(job_id=job.id, status=CANCEL_RESULTS[result])


@router.post("/runs/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(
    run: Run = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> RunCancelResponse:
    """
    Cancel every unfinished job of a run.

    :param run: Run the caller owns.
    :type run: Run
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: How many were cancelled now and how many are stopping.
    :rtype: RunCancelResponse
    """
    query = select(Job.id).where(
        Job.run_id == run.id, Job.status.not_in(FINAL_STATUSES)
    )
    job_ids = list((await db.execute(query)).scalars())
    results = [await request_cancel(db, job_id) for job_id in job_ids]
    await db.commit()
    return RunCancelResponse(
        run_id=run.id,
        cancelled=results.count(JobStatus.CANCELLED),
        cancelling=results.count(JobStatus.RUNNING),
    )
