"""
HTTP routes for script releases: the administrator publishes one (the
wheel as the request body), and anyone may ask which release new runs
use.

    curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \\
        --data-binary @afscripts-0.2.0-py3-none-any.whl \\
        "$API/api/releases?git_commit=2e6d386"

``python -m app.releases.publish`` builds the wheel and does this.
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_store, require_admin
from app.api.errors import conflict, too_large, unprocessable
from app.db.session import get_db
from app.models.user import User
from app.releases.published import PublishConflictError
from app.releases.service import latest_release, publish_release
from app.releases.wheel import (
    MAX_RELEASE_BYTES,
    TOO_BIG_MESSAGE,
    InvalidReleaseError,
)
from app.schemas.releases import ReleaseInfo
from app.storage.store import ArtifactStore

router = APIRouter(prefix="/releases", tags=["Releases"])
COMMIT_PATTERN = r"^[0-9a-f]{7,40}$"


async def read_upload(request: Request) -> bytes:
    """
    Read a release from the request body, refusing it as soon as it
    grows past ``MAX_RELEASE_BYTES``.

    :param request: The upload request.
    :type request: Request
    :return: The body.
    :rtype: bytes
    :raises HTTPException: 413 if the body is too big.
    """
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > MAX_RELEASE_BYTES:
            raise too_large(TOO_BIG_MESSAGE)
    return bytes(received)


@router.post(
    "",
    response_model=ReleaseInfo,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "This exact file was already published."},
        409: {"description": "This version exists with other contents."},
        422: {"description": "Not a release agents could run."},
    },
)
async def publish(
    request: Request,
    response: Response,
    git_commit: str | None = Query(None, pattern=COMMIT_PATTERN),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
) -> ReleaseInfo:
    """
    Publish a wheel as the newest release (administrator only).

    :param request: Carries the wheel as its body.
    :type request: Request
    :param response: Its status becomes 200 for a repeat publish.
    :type response: Response
    :param git_commit: The commit the wheel was built from.
    :type git_commit: str | None
    :param _admin: The administrator.
    :type _admin: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the wheel is kept.
    :type store: ArtifactStore
    :return: The release.
    :rtype: ReleaseInfo
    :raises HTTPException: 422 for an unusable wheel, 409 for a
        version that exists with other contents.
    """
    data = await read_upload(request)
    try:
        release, created = await publish_release(db, store, data, git_commit)
    except InvalidReleaseError as error:
        raise unprocessable(str(error)) from error
    except (PublishConflictError, IntegrityError) as error:
        # IntegrityError: the same version published at the same moment.
        raise conflict(str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return ReleaseInfo.model_validate(release)


@router.get("/current", response_model=ReleaseInfo | None)
async def current(db: AsyncSession = Depends(get_db)) -> ReleaseInfo | None:
    """
    The release new runs are pinned to.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The newest release, or null before the first.
    :rtype: ReleaseInfo | None
    """
    release = await latest_release(db)
    return ReleaseInfo.model_validate(release) if release else None
