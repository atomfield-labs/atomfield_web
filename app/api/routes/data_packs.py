"""
HTTP routes for data packs: the administrator uploads a zip once (the
request body, streamed to the store), and anyone may list the packs.

    curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \\
        --data-binary @pslibrary-rel-pbe.zip \\
        "$API/api/data-packs?name=pslibrary-rel-pbe&version=1.0.0&sha256=..."

``python -m app.releases.publish_data`` zips a folder and does this.
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_store, require_admin
from app.api.errors import conflict, too_large, unprocessable
from app.catalog.models import PACKAGE_NAME_PATTERN
from app.db.session import get_db
from app.models.user import User
from app.releases.data_packs import (
    DataPackUpload,
    InvalidDataPackError,
    list_data_packs,
    publish_data_pack,
)
from app.releases.published import PublishConflictError
from app.schemas.releases import DataPackInfo
from app.storage.store import ArtifactStore, TooLargeError

router = APIRouter(prefix="/data-packs", tags=["Data packs"])
NAME_QUERY = f"^{PACKAGE_NAME_PATTERN}$"
TOO_BIG_MESSAGE = "The pack is too big"
SHA256_QUERY = r"^[0-9a-f]{64}$"


@router.post(
    "",
    response_model=DataPackInfo,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "This exact pack was already published."},
        409: {"description": "This version exists with other contents."},
        413: {"description": "The pack is too big."},
        422: {"description": "Not a zip with the announced fingerprint."},
    },
)
async def publish(
    request: Request,
    response: Response,
    name: str = Query(pattern=NAME_QUERY),
    version: str = Query(pattern=NAME_QUERY),
    sha256: str = Query(pattern=SHA256_QUERY),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    store: ArtifactStore = Depends(get_store),
) -> DataPackInfo:
    """
    Publish a zip as a data pack (administrator only).

    :param request: Carries the zip as its body.
    :type request: Request
    :param response: Its status becomes 200 for a repeat publish.
    :type response: Response
    :param name: The pack's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :param sha256: The zip's fingerprint, computed by the publisher.
    :type sha256: str
    :param _admin: The administrator.
    :type _admin: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the zip is kept.
    :type store: ArtifactStore
    :return: The pack.
    :rtype: DataPackInfo
    :raises HTTPException: 409, 413 or 422, as described above.
    """
    upload = DataPackUpload(name, version, sha256)
    chunks = request.stream()
    try:
        pack, created = await publish_data_pack(db, store, upload, chunks)
    except TooLargeError as error:
        raise too_large(TOO_BIG_MESSAGE) from error
    except InvalidDataPackError as error:
        raise unprocessable(str(error)) from error
    except (PublishConflictError, IntegrityError) as error:
        # IntegrityError: the same version published at the same moment.
        raise conflict(str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return DataPackInfo.model_validate(pack)


@router.get("", response_model=list[DataPackInfo])
async def list_packs(
    db: AsyncSession = Depends(get_db),
) -> list[DataPackInfo]:
    """
    Every published data pack.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The packs, by name then version.
    :rtype: list[DataPackInfo]
    """
    return [
        DataPackInfo.model_validate(pack) for pack in await list_data_packs(db)
    ]
