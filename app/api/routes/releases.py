"""
HTTP routes for script releases: the administrator publishes one (the
bundle as the request body), and anyone may ask which release new runs
use. ``python -m app.releases.publish`` builds the bundle and sends it.
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_store, require_owner
from app.api.errors import conflict, not_found, too_large, unprocessable
from app.db.session import get_db
from app.models.user import User
from app.releases.bundle import (
    MAX_RELEASE_BYTES,
    TOO_BIG_MESSAGE,
    InvalidReleaseError,
)
from app.releases.published import PublishConflictError
from app.releases.service import (
    find_release,
    latest_release,
    publish_release,
)
from app.schemas.releases import ReleaseInfo
from app.storage.store import ArtifactStore

router = APIRouter(prefix="/releases", tags=["Releases"])
COMMIT_PATTERN = r"^[0-9a-f]{7,40}$"
RELEASE_KIND = "Release"


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
    _owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
) -> ReleaseInfo:
    """
    Publish a bundle as the newest release (administrator only).

    :param request: Carries the bundle as its body.
    :type request: Request
    :param response: Its status becomes 200 for a repeat publish.
    :type response: Response
    :param git_commit: The commit the bundle was built from.
    :type git_commit: str | None
    :param _owner: The owner.
    :type _owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the wheels are kept.
    :type store: ArtifactStore
    :return: The release.
    :rtype: ReleaseInfo
    :raises HTTPException: 422 for an unusable bundle, 409 for a
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


@router.get("/{name}/{version}", response_model=ReleaseInfo)
async def get_release(
    name: str, version: str, db: AsyncSession = Depends(get_db)
) -> ReleaseInfo:
    """
    A release by name and version, so a publisher can skip building one
    that is already there.

    :param name: Its name.
    :type name: str
    :param version: Its version.
    :type version: str
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The release.
    :rtype: ReleaseInfo
    :raises HTTPException: 404 if it was never published.
    """
    release = await find_release(db, name, version)
    if release is None:
        raise not_found(RELEASE_KIND, f"{name} {version}")
    return ReleaseInfo.model_validate(release)
