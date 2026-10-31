"""
HTTP routes for a person's pipelines: what the sessions page lists and
the editor opens and saves. Everyone sees only their own.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.errors import too_large
from app.core.identifiers import sanitize_identifier
from app.db.session import get_db
from app.models.user import User
from app.schemas.sessions import SessionDetail, SessionSave, SessionSummary
from app.services.sessions import save_session, session_of, sessions_of

router = APIRouter(prefix="/sessions", tags=["Sessions"])
# A draft holds its input files' text; browsers kept less than this.
MAX_SESSION_BYTES = 5 * 1024 * 1024
TOO_BIG_MESSAGE = (
    "This pipeline is too big to save: at most 5 MB, input files included."
)


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummary]:
    """
    The caller's pipelines, last changed first, each with how its newest
    run stands.

    :param user: The person asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Their pipelines.
    :rtype: list[SessionSummary]
    """
    return await sessions_of(db, user.id)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """
    One of the caller's pipelines, with its draft and newest run.

    :param session_id: The pipeline.
    :type session_id: str
    :param user: The person asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The pipeline.
    :rtype: SessionDetail
    """
    return await session_of(db, user.id, sanitize_identifier(session_id))


@router.put("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def put_session(
    session_id: str,
    payload: SessionSave,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Save what changed about one of the caller's pipelines, making it if
    it is new.

    :param session_id: The pipeline.
    :type session_id: str
    :param payload: What changed.
    :type payload: SessionSave
    :param request: The request, for the size of its body.
    :type request: Request
    :param user: The person asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: An empty answer.
    :rtype: Response
    :raises HTTPException: 413 for a draft over the limit.
    """
    if len(await request.body()) > MAX_SESSION_BYTES:
        raise too_large(TOO_BIG_MESSAGE)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        changes["title"] = (changes["title"] or "").strip() or None
    await save_session(db, user.id, sanitize_identifier(session_id), changes)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
