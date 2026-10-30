"""
Compute targets: create, list, rotate a token, retire, and check that
a submission may use one. A user may run on their own targets and on
the shared AtomField server, never on someone else's.
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import not_found
from app.core.security import generate_agent_token
from app.models.compute_target import HOUSE_TARGET_ID, ComputeTarget
from app.runs.lifecycle import cancel_jobs, on_target
from app.schemas.targets import TargetCreate, TargetInfo, TargetToken

# Agents call in at least every 30 s (claims and heartbeats).
ONLINE_WINDOW = timedelta(seconds=90)
# Missing, retired or not yours: the same 404, so strangers learn
# nothing.
TARGET_KIND = "Compute target"
TARGET_REMOVED_MESSAGE = "Cancelled: its compute target was removed"


def visible_to(owner_id: uuid.UUID):
    """
    Condition: a live target the user may run on.

    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID
    :return: SQL condition.
    :rtype: ColumnElement[bool]
    """
    mine_or_shared = or_(
        ComputeTarget.owner_id == owner_id,
        ComputeTarget.id == HOUSE_TARGET_ID,
    )
    return mine_or_shared & ComputeTarget.retired_at.is_(None)


async def list_targets(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> list[TargetInfo]:
    """
    The targets a user may run on: the shared server first, then
    theirs, newest first.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID
    :return: Targets with their online state.
    :rtype: list[TargetInfo]
    """
    online = ComputeTarget.last_seen_at > func.now() - ONLINE_WINDOW
    query = (
        select(ComputeTarget, online.label("online"))
        .where(visible_to(owner_id))
        .order_by(
            (ComputeTarget.id != HOUSE_TARGET_ID),
            ComputeTarget.created_at.desc(),
        )
    )
    rows = (await db.execute(query)).all()
    return [describe(target, bool(is_online)) for target, is_online in rows]


def describe(target: ComputeTarget, online: bool) -> TargetInfo:
    """
    A target as the API shows it.

    :param target: The row.
    :type target: ComputeTarget
    :param online: Whether its agent called in recently.
    :type online: bool
    :return: Public description.
    :rtype: TargetInfo
    """
    return TargetInfo(
        id=target.id,
        name=target.name,
        kind=target.kind,
        shared=target.id == HOUSE_TARGET_ID,
        last_seen_at=target.last_seen_at,
        online=online,
    )


async def add_target(
    db: AsyncSession,
    owner_id: uuid.UUID,
    request: TargetCreate,
) -> ComputeTarget:
    """
    Register a new place to run jobs, flushed but without a token: it
    gets one next (``create_target``), or when its agent collects one
    after pairing.

    Results stay where its jobs run, so its runs are not zipped and
    uploaded automatically.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param owner_id: The person it belongs to.
    :type owner_id: uuid.UUID
    :param request: Name and kind.
    :type request: TargetCreate
    :return: The target.
    :rtype: ComputeTarget
    """
    target = ComputeTarget(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=request.name,
        kind=request.kind,
        bundles_automatically=False,
    )
    db.add(target)
    await db.flush()
    return target


async def create_target(
    db: AsyncSession,
    owner_id: uuid.UUID,
    request: TargetCreate,
) -> TargetToken:
    """
    Register a new place to run jobs, with a fresh agent token.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The person it belongs to.
    :type owner_id: uuid.UUID
    :param request: Name and kind.
    :type request: TargetCreate
    :return: The target and its token (shown once).
    :rtype: TargetToken
    """
    target = await add_target(db, owner_id, request)
    token, target.token_hash = generate_agent_token()
    await db.commit()
    await db.refresh(target)
    return TargetToken(target=describe(target, False), token=token)


async def owned_target(
    db: AsyncSession,
    owner_id: uuid.UUID,
    target_id: uuid.UUID,
) -> ComputeTarget:
    """
    A live target the user owns (the shared server is not theirs to
    change).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID
    :param target_id: Requested target.
    :type target_id: uuid.UUID
    :return: The target.
    :rtype: ComputeTarget
    :raises HTTPException: 404 if missing, retired or not theirs.
    """
    target = await db.get(ComputeTarget, target_id)
    owned = target is not None and target.owner_id == owner_id
    if not owned or target.retired_at is not None:
        raise not_found(TARGET_KIND, target_id)
    return target


async def rotate_token(
    db: AsyncSession,
    owner_id: uuid.UUID,
    target_id: uuid.UUID,
) -> TargetToken:
    """
    Replace a target's token (lost or leaked); the old one stops
    working at once.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID
    :param target_id: The target.
    :type target_id: uuid.UUID
    :return: The target and its new token (shown once).
    :rtype: TargetToken
    """
    target = await owned_target(db, owner_id, target_id)
    token, target.token_hash = generate_agent_token()
    await db.commit()
    return TargetToken(target=describe(target, False), token=token)


async def retire_target(
    db: AsyncSession,
    owner_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    """
    Retire a target: hidden from the list and its token stops working,
    while its past runs keep pointing at it. Its unfinished jobs are
    cancelled, since no agent can run them any more.

    :param db: Asynchronous database session; the caller commits with
        ``commit_and_publish``.
    :type db: AsyncSession
    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID
    :param target_id: The target.
    :type target_id: uuid.UUID
    """
    target = await owned_target(db, owner_id, target_id)
    await db.execute(
        update(ComputeTarget)
        .where(ComputeTarget.id == target.id)
        .values(retired_at=func.now(), token_hash=None)
    )
    await cancel_jobs(db, on_target(target.id), TARGET_REMOVED_MESSAGE)


async def usable_target(
    db: AsyncSession,
    owner_id: uuid.UUID | None,
    target_id: uuid.UUID | None,
) -> uuid.UUID:
    """
    The target a submission will run on: the shared server unless the
    user names one of their own.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param owner_id: The submitting user.
    :type owner_id: uuid.UUID | None
    :param target_id: The target asked for, if any.
    :type target_id: uuid.UUID | None
    :return: The target's id.
    :rtype: uuid.UUID
    :raises HTTPException: 404 for a target the user may not use.
    """
    if target_id is None or target_id == HOUSE_TARGET_ID:
        return HOUSE_TARGET_ID
    query = select(ComputeTarget.id).where(
        ComputeTarget.id == target_id, visible_to(owner_id)
    )
    if (await db.execute(query)).scalar_one_or_none() is None:
        raise not_found(TARGET_KIND, target_id)
    return target_id
