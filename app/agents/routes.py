"""
HTTP routes of the agent API. Every route requires an agent token.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auth import get_agent_target
from app.agents.schemas import (
    BundleReport,
    ClaimRequest,
    CompletionRequest,
    CompletionResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    JobAssignment,
    UploadLinksRequest,
    UploadLinksResponse,
)
from app.agents.service import (
    AgentServices,
    claim_next,
    hand_out_packs,
    record_heartbeat,
    report_bundle,
    report_completion,
    upload_links,
)
from app.db.session import get_db
from app.models.compute_target import ComputeTarget
from app.storage.store import InvalidKeyError

router = APIRouter(prefix="/agent", tags=["Agents"])


async def get_agent_services(request: Request) -> AgentServices:
    """
    Gather the shared parts created at startup.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Queue, bus, catalogs and store.
    :rtype: AgentServices
    """
    state = request.app.state
    return AgentServices(
        queue=state.job_queue,
        bus=state.event_bus,
        catalogs=state.catalogs,
        store=state.store,
    )


@router.post(
    "/claims",
    response_model=JobAssignment,
    responses={204: {"description": "No job arrived while waiting."}},
)
async def claim(
    request: ClaimRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    services: AgentServices = Depends(get_agent_services),
):
    """
    Give the calling agent one job, waiting up to ``wait_seconds``.

    :param request: How long the agent is willing to wait.
    :type request: ClaimRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :return: The assignment, or an empty 204 response.
    :rtype: JobAssignment | Response
    """
    assignment = await claim_next(
        db, services, target, request.wait_seconds, request.scheduled
    )
    if assignment is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return assignment


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: HeartbeatRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    services: AgentServices = Depends(get_agent_services),
) -> HeartbeatResponse:
    """
    Renew the leases of the attempts the agent is running.

    :param request: Attempts the agent is running.
    :type request: HeartbeatRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :return: Attempts to cancel or abandon, and runs to zip.
    :rtype: HeartbeatResponse
    """
    return await record_heartbeat(
        db, services, target, request.jobs, request.started
    )


@router.post("/jobs/{job_id}/complete", response_model=CompletionResponse)
async def complete(
    job_id: uuid.UUID,
    request: CompletionRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    services: AgentServices = Depends(get_agent_services),
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
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :return: The recorded outcome.
    :rtype: CompletionResponse
    :raises HTTPException: 409 if the attempt no longer owns the job.
    """
    completion = await report_completion(db, services, target, job_id, request)
    if completion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This attempt no longer owns the job; nothing recorded.",
        )
    return CompletionResponse(
        job_id=completion.job.id,
        status=completion.job.status,
        children_queued=len(completion.ready),
        pack=await hand_out_packs(db, services.store, target),
    )


@router.post("/jobs/{job_id}/uploads", response_model=UploadLinksResponse)
async def uploads(
    job_id: uuid.UUID,
    request: UploadLinksRequest,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
    services: AgentServices = Depends(get_agent_services),
) -> UploadLinksResponse:
    """
    Hand out upload links for a finishing attempt's small files.

    :param job_id: The job whose files these are.
    :type job_id: uuid.UUID
    :param request: Attempt and file names.
    :type request: UploadLinksRequest
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param services: Queue, bus, catalogs and store.
    :type services: AgentServices
    :return: One link per name.
    :rtype: UploadLinksResponse
    :raises HTTPException: 409 if the attempt no longer holds the job;
        422 for a name that is not a plain file name.
    """
    try:
        links = await upload_links(db, services, target, job_id, request)
    except InvalidKeyError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Not a plain file name: {error}",
        ) from None
    if links is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This attempt no longer owns the job; nothing to upload.",
        )
    return links


@router.post("/runs/{run_id}/bundle", status_code=status.HTTP_204_NO_CONTENT)
async def bundle(
    run_id: uuid.UUID,
    request: BundleReport,
    target: ComputeTarget = Depends(get_agent_target),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Record how zipping and uploading a run ended.

    :param run_id: The run.
    :type run_id: uuid.UUID
    :param request: Ready (with size), too big, or failed (with why).
    :type request: BundleReport
    :param target: Calling agent's target.
    :type target: ComputeTarget
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Empty response.
    :rtype: Response
    :raises HTTPException: 409 if this agent was not packing the run.
    """
    if not await report_bundle(db, target, run_id, request):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This run was not being packed here."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
