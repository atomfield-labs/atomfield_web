"""
The storage route behind ``LocalDiskStore``'s signed links.

No API key here: the link itself is the permission. Every request is
checked against the signature before anything is read or written.
"""

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.dependencies import get_store
from app.storage.links import DOWNLOAD, UPLOAD, LinkGrant
from app.storage.store import InvalidKeyError, LocalDiskStore, TooLargeError

router = APIRouter(prefix="/storage", tags=["Storage"])
CONTENT_LENGTH = "content-length"


class UploadReceipt(BaseModel):
    """
    What an accepted upload stored.
    """

    key: str
    size_bytes: int


def check_link(store: LocalDiskStore, grant: LinkGrant, signature: str) -> None:
    """
    Refuse the request unless the link was signed for exactly it.

    :param store: The store whose signer issued the link.
    :type store: LocalDiskStore
    :param grant: What the request asks to do.
    :type grant: LinkGrant
    :param signature: Signature carried by the link.
    :type signature: str
    :raises HTTPException: 403 if tampered with or expired.
    """
    if not store.signer.verify(grant, signature, time.time()):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Link is invalid or has expired"
        )


@router.get("/{key:path}", response_class=FileResponse)
async def download(
    key: str,
    expires: int,
    signature: str,
    filename: str = "",
    store: LocalDiskStore = Depends(get_store),
) -> FileResponse:
    """
    Serve the file a download link names.

    :param key: Stored file.
    :type key: str
    :param expires: Expiry from the link.
    :type expires: int
    :param signature: Signature from the link.
    :type signature: str
    :param filename: Name to save as, from the link.
    :type filename: str
    :param store: The server's store.
    :type store: LocalDiskStore
    :return: The file, as an attachment.
    :rtype: FileResponse
    :raises HTTPException: 403 for a bad link, 404 if the file is gone.
    """
    check_link(store, LinkGrant(DOWNLOAD, key, expires, 0, filename), signature)
    path = store.existing_path(key)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(path, filename=filename or Path(key).name)


@router.put(
    "/{key:path}",
    response_model=UploadReceipt,
    status_code=status.HTTP_201_CREATED,
)
async def upload(
    key: str,
    expires: int,
    signature: str,
    request: Request,
    max_bytes: int = 0,
    store: LocalDiskStore = Depends(get_store),
) -> UploadReceipt:
    """
    Store the body of an upload link's request, streamed to disk.

    :param key: Where to store the file.
    :type key: str
    :param expires: Expiry from the link.
    :type expires: int
    :param signature: Signature from the link.
    :type signature: str
    :param request: The request whose body is the file.
    :type request: Request
    :param max_bytes: Size limit from the link; absent from a download
        link, which then fails the signature check (403).
    :type max_bytes: int
    :param store: The server's store.
    :type store: LocalDiskStore
    :return: What was stored.
    :rtype: UploadReceipt
    :raises HTTPException: 403 for a bad link, 413 if too large.
    """
    check_link(store, LinkGrant(UPLOAD, key, expires, max_bytes), signature)
    declared = int(request.headers.get(CONTENT_LENGTH) or 0)
    try:
        if declared > max_bytes:
            raise TooLargeError(key)
        size = await store.save_stream(key, request.stream(), max_bytes)
    except TooLargeError:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Upload exceeds this link's limit of {max_bytes} bytes",
        ) from None
    except InvalidKeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad key") from None
    return UploadReceipt(key=key, size_bytes=size)
