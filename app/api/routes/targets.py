"""
HTTP routes for compute targets: where a user's runs can execute.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.targets import (
    create_target,
    list_targets,
    retire_target,
    rotate_token,
)
from app.api.dependencies import get_current_api_key, get_event_bus
from app.db.session import get_db
from app.events.bus import EventBus
from app.events.changes import commit_and_publish
from app.models.api_key import ApiKey
from app.schemas.targets import TargetCreate, TargetInfo, TargetToken

router = APIRouter(prefix="/targets", tags=["Compute targets"])


@router.get("", response_model=list[TargetInfo])
async def get_targets(
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[TargetInfo]:
    """
    Where the caller can run jobs: the shared server and their own.

    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Targets with their online state.
    :rtype: list[TargetInfo]
    """
    return await list_targets(db, api_key.id)


@router.post(
    "", response_model=TargetToken, status_code=status.HTTP_201_CREATED
)
async def add_target(
    request: TargetCreate,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> TargetToken:
    """
    Add a cluster or computer; returns its agent token, shown once.

    :param request: Name and kind.
    :type request: TargetCreate
    :param api_key: Authenticated caller.
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The target and its token.
    :rtype: TargetToken
    """
    return await create_target(db, api_key.id, request)


@router.post("/{target_id}/token", response_model=TargetToken)
async def new_token(
    target_id: uuid.UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> TargetToken:
    """
    Replace a target's agent token; the old one stops working.

    :param target_id: The target.
    :type target_id: uuid.UUID
    :param api_key: Authenticated caller (must own the target).
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The target and its new token.
    :rtype: TargetToken
    """
    return await rotate_token(db, api_key.id, target_id)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_target(
    target_id: uuid.UUID,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> Response:
    """
    Retire a target: its token stops working, it leaves the list, and
    its unfinished jobs are cancelled; its past runs keep their
    history.

    :param target_id: The target.
    :type target_id: uuid.UUID
    :param api_key: Authenticated caller (must own the target).
    :type api_key: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param bus: Where the cancelled jobs are announced.
    :type bus: EventBus
    :return: Empty response.
    :rtype: Response
    """
    await retire_target(db, api_key.id, target_id)
    await commit_and_publish(db, bus)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
