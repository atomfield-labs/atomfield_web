"""
HTTP routes for script releases: the administrator publishes one (the
wheel as the request body), and anyone may ask which release new runs
use.

    curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \\
        --data-binary @afscripts-0.2.0-py3-none-any.whl \\
        "$API/api/releases?git_commit=2e6d386"

``python -m app.releases.publish`` builds the wheel and does this.
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_store, require_admin_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.releases.service import (
    ReleaseConflictError,
    latest_release,
    publish_release,
)
from app.releases.wheel import MAX_RELEASE_BYTES, InvalidReleaseError
from app.schemas.releases import ReleaseInfo
from app.storage.store import ArtifactStore

router = APIRouter(prefix="/releases", tags=["Releases"])
COMMIT_PATTERN = r"^[0-9a-f]{7,40}$"


async def read_upload(request: Request, max_bytes: int) -> bytes:
    """
    Read the request body, refusing it as soon as it grows too big.

    :param request: The upload request.
    :type request: Request
    :param max_bytes: Largest body accepted.
    :type max_bytes: int
    :return: The body.
    :rtype: bytes
    :raises HTTPException: 413 if the body is too big.
    """
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"A release may be at most {max_bytes} bytes",
            )
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
    _admin: ApiKey = Depends(require_admin_key),
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
    :param _admin: The administrator's key.
    :type _admin: ApiKey
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the wheel is kept.
    :type store: ArtifactStore
    :return: The release.
    :rtype: ReleaseInfo
    :raises HTTPException: 422 for an unusable wheel, 409 for a
        version that exists with other contents.
    """
    data = await read_upload(request, MAX_RELEASE_BYTES)
    try:
        release, created = await publish_release(db, store, data, git_commit)
    except InvalidReleaseError as error:
        raise HTTPException(422, detail=str(error)) from error
    except (ReleaseConflictError, IntegrityError) as error:
        # IntegrityError: the same version published at the same moment.
        raise HTTPException(409, detail=str(error)) from error
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
