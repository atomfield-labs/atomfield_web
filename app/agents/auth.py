"""
Agent identity: bearer tokens, stored only as hashes.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.compute_target import HOUSE_TARGET_ID, ComputeTarget

BEARER = "bearer"


def unauthorized(detail: str) -> HTTPException:
    """
    Build a 401 that tells the client which scheme to use.

    :param detail: Explanation for the client.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_agent_target(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> ComputeTarget:
    """
    Identify the calling agent from ``Authorization: Bearer <token>``.

    :param authorization: Raw Authorization header.
    :type authorization: str | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The compute target the token belongs to.
    :rtype: ComputeTarget
    :raises HTTPException: 401 for a missing or unknown token.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != BEARER or not token:
        raise unauthorized("Agent token required: Authorization: Bearer ...")
    query = select(ComputeTarget).where(
        ComputeTarget.token_hash == hash_api_key(token)
    )
    target = (await db.execute(query)).scalars().first()
    if target is None:
        raise unauthorized("Unknown agent token.")
    return target


async def provision_house_target(db: AsyncSession) -> None:
    """
    Give the house agent the token from ``HOUSE_AGENT_TOKEN``.

    Re-run at every start, so rotating the token is "change the
    environment variable, restart". The row itself comes from a
    migration.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    """
    if not settings.HOUSE_AGENT_TOKEN:
        return
    statement = (
        update(ComputeTarget)
        .where(ComputeTarget.id == HOUSE_TARGET_ID)
        .values(token_hash=hash_api_key(settings.HOUSE_AGENT_TOKEN))
    )
    await db.execute(statement)
    await db.commit()


async def touch_target(db: AsyncSession, target: ComputeTarget) -> None:
    """
    Record that a target's agent was just heard from.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param target: Calling agent's target.
    :type target: ComputeTarget
    """
    await db.execute(
        update(ComputeTarget)
        .where(ComputeTarget.id == target.id)
        .values(last_seen_at=func.now())
    )
