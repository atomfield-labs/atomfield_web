"""
HTTP routes for pairing an agent with a short code. The agent asks and
waits (it has no token yet, so nothing to sign in with); the person
approves the code in the web app, signed in.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pairing import (
    PAIRING_SECONDS,
    POLL_SECONDS,
    Pairing,
    Pairings,
    normalize_code,
    shown_code,
)
from app.agents.targets import add_target, describe, rotate_token
from app.api.dependencies import (
    SECONDS_PER_MINUTE,
    client_address,
    code_lookup_allowed,
    get_browser_user,
    get_redis,
    pairing_start_allowed,
)
from app.api.errors import conflict, not_found, too_many_requests
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.pairings import (
    PairingApproval,
    PairingPoll,
    PairingRequest,
    PairingStarted,
    PairingView,
)
from app.schemas.targets import TargetCreate, TargetInfo, TargetToken

agent_router = APIRouter(prefix="/agent/pairings", tags=["Agents"])
router = APIRouter(prefix="/pairings", tags=["Compute targets"])

# Unknown, expired, approved or not yours: the same 404 each time.
PAIRING_KIND = "Pairing"
TOO_MANY_STARTS = "Too many pairings asked from this address; wait a minute."
TOO_MANY_CODES = "Too many codes tried; wait a minute."
ALREADY_APPROVED = "This code was approved a moment ago."
APPROVE_PAGE = "{origin}/#pair/{code}"


async def get_pairings(redis: Redis = Depends(get_redis)) -> Pairings:
    """
    Provide the pairings in progress.

    :param redis: Shared Redis client.
    :type redis: Redis
    :return: The pairings.
    :rtype: Pairings
    """
    return Pairings(redis)


def approve_url(code: str) -> str | None:
    """
    The web app's page for approving a code, when the server knows its
    own address (from the sign-in settings).

    :param code: The code.
    :type code: str
    :return: The link, or None.
    :rtype: str | None
    """
    origin = settings.public_origin
    if not origin:
        return None
    return APPROVE_PAGE.format(origin=origin, code=shown_code(code))


@agent_router.post(
    "", response_model=PairingStarted, status_code=status.HTTP_201_CREATED
)
async def start_pairing(
    payload: PairingRequest,
    request: Request,
    pairings: Pairings = Depends(get_pairings),
    allowed: bool = Depends(pairing_start_allowed),
) -> PairingStarted:
    """
    An agent asks to be paired. It gets a code to show the person, and
    a secret to collect its token with once they approve.

    :param payload: What the agent says about its machine.
    :type payload: PairingRequest
    :param request: Incoming request (its address is shown).
    :type request: Request
    :param pairings: Pairings in progress.
    :type pairings: Pairings
    :param allowed: Whether this address may ask again.
    :type allowed: bool
    :return: Code, secret, and how often to ask back.
    :rtype: PairingStarted
    :raises HTTPException: 429 past the per-address limit.
    """
    if not allowed:
        raise too_many_requests(TOO_MANY_STARTS, SECONDS_PER_MINUTE)
    pairing, secret = await pairings.start(payload, client_address(request))
    return PairingStarted(
        code=shown_code(pairing.code),
        secret=secret,
        approve_url=approve_url(pairing.code),
        expires_in=PAIRING_SECONDS,
        interval=POLL_SECONDS,
    )


@agent_router.post(
    "/{code}/token",
    response_model=TargetToken,
    responses={202: {"description": "Not approved yet; ask again."}},
)
async def collect_token(
    code: str,
    payload: PairingPoll,
    pairings: Pairings = Depends(get_pairings),
    db: AsyncSession = Depends(get_db),
) -> TargetToken | Response:
    """
    The agent asks whether its code was approved; once it is, it gets
    its token, this once.

    :param code: The code it showed.
    :type code: str
    :param payload: The secret only the asking agent holds.
    :type payload: PairingPoll
    :param pairings: Pairings in progress.
    :type pairings: Pairings
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The new cluster and its token, or 202 while waiting.
    :rtype: TargetToken | Response
    :raises HTTPException: 404 for an unknown or expired code, or a
        secret that is not the asking agent's: the code alone is
        worth nothing.
    """
    pairing = await pairings.find(normalize_code(code))
    if pairing is None or not pairing.asked_by(payload.secret):
        raise not_found(PAIRING_KIND, code)
    if not pairing.approved:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    if await pairings.take(pairing.code) is None:
        raise not_found(PAIRING_KIND, code)
    owner_id = uuid.UUID(pairing.owner_id)
    return await rotate_token(db, owner_id, uuid.UUID(pairing.target_id))


async def waiting_pairing(
    code: str, pairings: Pairings, allowed: bool
) -> Pairing:
    """
    The pairing a person is looking at: it must exist, and still wait
    for approval.

    :param code: The code as typed.
    :type code: str
    :param pairings: Pairings in progress.
    :type pairings: Pairings
    :param allowed: Whether this address may try another code.
    :type allowed: bool
    :return: The pairing.
    :rtype: Pairing
    :raises HTTPException: 429 past the limit on codes tried; 404 for
        an unknown, expired or already approved code.
    """
    if not allowed:
        raise too_many_requests(TOO_MANY_CODES, SECONDS_PER_MINUTE)
    pairing = await pairings.find(normalize_code(code))
    if pairing is None or pairing.approved:
        raise not_found(PAIRING_KIND, code)
    return pairing


@router.get(
    "/{code}",
    response_model=PairingView,
    dependencies=[Depends(get_browser_user)],
)
async def see_pairing(
    code: str,
    pairings: Pairings = Depends(get_pairings),
    allowed: bool = Depends(code_lookup_allowed),
) -> PairingView:
    """
    What is asking to be paired with this code, so the person can tell
    it is their own machine before approving.

    :param code: The code as typed.
    :type code: str
    :param pairings: Pairings in progress.
    :type pairings: Pairings
    :param allowed: Whether this address may try another code.
    :type allowed: bool
    :return: The machine's name, user and address, and when it asked.
    :rtype: PairingView
    """
    pairing = await waiting_pairing(code, pairings, allowed)
    view = PairingView.model_validate(pairing)
    return view.model_copy(update={"code": shown_code(pairing.code)})


@router.post("/{code}", response_model=TargetInfo)
async def approve_pairing(
    code: str,
    payload: PairingApproval,
    user: User = Depends(get_browser_user),
    pairings: Pairings = Depends(get_pairings),
    allowed: bool = Depends(code_lookup_allowed),
    db: AsyncSession = Depends(get_db),
) -> TargetInfo:
    """
    Approve a pairing: the machine becomes a new cluster of the
    person's, and its agent collects its token next. The cluster is
    saved before the pairing is marked, so an agent never collects a
    token for a cluster that does not exist.

    :param code: The code as typed.
    :type code: str
    :param payload: The new cluster's name.
    :type payload: PairingApproval
    :param user: The person, signed in.
    :type user: User
    :param pairings: Pairings in progress.
    :type pairings: Pairings
    :param allowed: Whether this address may try another code.
    :type allowed: bool
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The new cluster.
    :rtype: TargetInfo
    :raises HTTPException: 409 if the code was approved a moment ago.
    """
    pairing = await waiting_pairing(code, pairings, allowed)
    if not await pairings.claim_approval(pairing.code):
        raise conflict(ALREADY_APPROVED)
    wanted = TargetCreate(name=payload.name, kind=pairing.kind)
    target = await add_target(db, user.id, wanted)
    await db.commit()
    await pairings.approve(pairing, user.id, target.id)
    return describe(target, False)
