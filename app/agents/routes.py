"""
HTTP routes of the agent API. Every route requires an agent token.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auth import get_agent_target
from app.agents.schemas import (
    ClaimRequest,
    CompletionRequest,
    CompletionResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    JobAssignment,
)
from app.agents.service import claim_next, record_heartbeat, report_completion
from app.api.dependencies import get_catalog, get_job_queue
from app.catalog.catalog import Catalog
from app.db.session import get_db
from app.models.compute_target import ComputeTarget
from app.queue.job_queue import RedisJobQueue

router = APIRouter(prefix="/agent", tags=["Agents"])


@router.post(
    "/claims",
    response_model=JobAssignment,
    responses={204: {"description": "No job arrived while waiting."}},
)
async def claim(
    request: ClaimRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
    catalog: Catalog = Depends(get_catalog),
):
    """
    Give the calling agent one job, waiting up to ``wait_seconds``.

    :param request: How long the agent is willing to wait.
    :type request: ClaimRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue.
    :type queue: RedisJobQueue
    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :return: The assignment, or an empty 204 response.
    :rtype: JobAssignment | Response
    """
    assignment = await claim_next(
        db, queue, catalog, target, request.wait_seconds
    )
    if assignment is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return assignment


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: HeartbeatRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatResponse:
    """
    Renew the leases of the attempts the agent is running.

    :param request: Attempts the agent is running.
    :type request: HeartbeatRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Attempts to cancel or abandon.
    :rtype: HeartbeatResponse
    """
    return await record_heartbeat(db, target, request.jobs)


@router.post("/jobs/{job_id}/complete", response_model=CompletionResponse)
async def complete(
    job_id: uuid.UUID,
    request: CompletionRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    queue: RedisJobQueue = Depends(get_job_queue),
) -> CompletionResponse:
    """
    Record how one attempt ended.

    :param job_id: Finished job.
    :type job_id: uuid.UUID
    :param request: Attempt number and outcome.
    :type request: CompletionRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param queue: Job queue.
    :type queue: RedisJobQueue
    :return: The recorded outcome.
    :rtype: CompletionResponse
    :raises HTTPException: 409 if the attempt no longer owns the job.
    """
    completion = await report_completion(db, queue, target, job_id, request)
    if completion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This attempt no longer owns the job; nothing recorded.",
        )
    return CompletionResponse(
        job_id=completion.job.id,
        status=completion.job.status,
        children_queued=len(completion.ready),
    )
