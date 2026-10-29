"""
Where the server keeps files: an ``ArtifactStore``.

Callers never touch paths. They write and read small files by key,
and hand out signed links for big transfers, so the bytes of a zip go
straight between the agent or browser and the store. Today the store
is a folder on the server (``LocalDiskStore``, whose links point at
our own ``/api/storage`` route); a cloud store would issue its own
links and nothing else would change.
"""

import asyncio
import os
import shutil
import time
import uuid
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode

from app.core.names import is_plain_name
from app.storage.links import DOWNLOAD, UPLOAD, LinkGrant, LinkSigner

LINK_PREFIX = "/api/storage"


class InvalidKeyError(ValueError):
    """
    A key that could escape the store's folder or break a signature.
    """


class TooLargeError(ValueError):
    """
    An upload went past the size its link allows.
    """


def is_safe_key(key: str) -> bool:
    """
    Whether a key is plain names joined by ``/``: so no ``..``, no
    absolute path ("/abs" starts with an empty name), no backslashes
    or control characters.

    :param key: Proposed key, e.g. ``runs/<run>/bundle.zip``.
    :type key: str
    :return: True if it can neither escape the store nor break a
        signature.
    :rtype: bool
    """
    return all(is_plain_name(part) for part in key.split("/"))


def validate_key(key: str) -> str:
    """
    Accept only relative, plain keys: no ``..``, no absolute paths, no
    backslashes or control characters.

    :param key: Proposed key, e.g. ``runs/<run>/bundle.zip``.
    :type key: str
    :return: The key, unchanged.
    :rtype: str
    :raises InvalidKeyError: If the key is unsafe.
    """
    if not is_safe_key(key):
        raise InvalidKeyError(key)
    return key


def validate_filename(filename: str) -> str:
    """
    Accept a download name only if it is one plain file name.

    :param filename: Name the browser saves a download as.
    :type filename: str
    :return: The name, unchanged.
    :rtype: str
    :raises InvalidKeyError: If it is empty, a path, or unsafe.
    """
    if not is_plain_name(filename):
        raise InvalidKeyError(filename)
    return filename


class ArtifactStore(Protocol):
    """
    Keeps files by key and issues links to them.
    """

    def upload_link(self, key: str, max_bytes: int, valid_seconds: int) -> str:
        """
        A link that accepts uploads of at most ``max_bytes`` to key
        until it expires.

        :param key: Where the file will be stored.
        :type key: str
        :param max_bytes: Size limit.
        :type max_bytes: int
        :param valid_seconds: How long the link works.
        :type valid_seconds: int
        :return: The link.
        :rtype: str
        """

    def download_link(
        self,
        key: str,
        valid_seconds: int,
        filename: str = "",
    ) -> str:
        """
        A link that downloads one file.

        :param key: The file.
        :type key: str
        :param valid_seconds: How long the link works.
        :type valid_seconds: int
        :param filename: Name to save as; the key's last part if empty.
        :type filename: str
        :return: The link.
        :rtype: str
        """

    async def save_stream(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> int:
        """
        Store a big file as it arrives, never all in memory; it appears
        only when complete.

        :param key: Where to store it.
        :type key: str
        :param chunks: Its bytes, in pieces.
        :type chunks: AsyncIterable[bytes]
        :param max_bytes: Size limit.
        :type max_bytes: int
        :return: Bytes stored.
        :rtype: int
        :raises TooLargeError: If it passes the limit.
        """

    async def write(self, key: str, data: bytes) -> None:
        """
        Store a small file (replacing any file with that key).

        :param key: Where to store it.
        :type key: str
        :param data: Its content.
        :type data: bytes
        """

    async def read(self, key: str) -> bytes | None:
        """
        Read a small file.

        :param key: The file.
        :type key: str
        :return: Its content, or None if absent.
        :rtype: bytes | None
        """

    async def delete(self, key: str) -> None:
        """
        Remove a file; removing an absent file is fine.

        :param key: The file.
        :type key: str
        """

    async def list_names(self, folder: str) -> list[str]:
        """
        Names of the files directly inside a folder.

        :param folder: Key prefix such as ``uploads/<user>/<session>``.
        :type folder: str
        :return: File names, sorted; empty if there are none.
        :rtype: list[str]
        """

    async def delete_folder(self, folder: str) -> None:
        """
        Remove every file under a key prefix; an absent one is fine.

        :param folder: Key prefix such as ``runs/<run>``.
        :type folder: str
        """


class LocalDiskStore:
    """
    A store in a folder on the server, with links to ``/api/storage``.
    """

    def __init__(self, root: Path, signer: LinkSigner) -> None:
        """
        :param root: Folder holding every stored file.
        :type root: Path
        :param signer: Signs and checks links.
        :type signer: LinkSigner
        """
        self.root = root.resolve()
        self.signer = signer

    def path_for(self, key: str) -> Path:
        """
        Map a key to its file under the root.

        :param key: The file's key.
        :type key: str
        :return: Absolute path inside the root.
        :rtype: Path
        :raises InvalidKeyError: If the key is unsafe.
        """
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise InvalidKeyError(key)
        return path

    def link(self, grant: LinkGrant) -> str:
        """
        Turn a grant into a URL on our storage route.

        :param grant: What the link allows.
        :type grant: LinkGrant
        :return: Path and query, relative to the API's address.
        :rtype: str
        """
        query = {"expires": grant.expires}
        if grant.max_bytes:
            query["max_bytes"] = grant.max_bytes
        if grant.filename:
            query["filename"] = grant.filename
        query["signature"] = self.signer.sign(grant)
        return f"{LINK_PREFIX}/{quote(grant.key)}?{urlencode(query)}"

    def upload_link(self, key: str, max_bytes: int, valid_seconds: int) -> str:
        """
        A link that accepts uploads of at most ``max_bytes`` to key
        until it expires.

        :param key: Where the file will be stored.
        :type key: str
        :param max_bytes: Size limit.
        :type max_bytes: int
        :param valid_seconds: How long the link works.
        :type valid_seconds: int
        :return: The link.
        :rtype: str
        """
        expires = int(time.time()) + valid_seconds
        grant = LinkGrant(UPLOAD, validate_key(key), expires, max_bytes)
        return self.link(grant)

    def download_link(
        self,
        key: str,
        valid_seconds: int,
        filename: str = "",
    ) -> str:
        """
        A link that downloads one file.

        :param key: The file.
        :type key: str
        :param valid_seconds: How long the link works.
        :type valid_seconds: int
        :param filename: Name to save as; the key's last part if empty.
        :type filename: str
        :return: The link.
        :rtype: str
        """
        expires = int(time.time()) + valid_seconds
        if filename:
            validate_filename(filename)
        grant = LinkGrant(DOWNLOAD, validate_key(key), expires, 0, filename)
        return self.link(grant)

    async def write(self, key: str, data: bytes) -> None:
        """
        Store a small file atomically: written aside, then renamed, so
        a reader never sees half a file.

        :param key: Where to store it.
        :type key: str
        :param data: Its content.
        :type data: bytes
        """
        path = self.path_for(key)
        await asyncio.to_thread(write_atomically, path, data)

    async def save_stream(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> int:
        """
        Store an upload as it arrives, refusing it once it passes the
        limit. The file appears only when complete.

        :param key: Where to store it.
        :type key: str
        :param chunks: The request body.
        :type chunks: AsyncIterable[bytes]
        :param max_bytes: Size limit from the link.
        :type max_bytes: int
        :return: Bytes stored.
        :rtype: int
        :raises TooLargeError: If the upload passes the limit.
        """
        path = self.path_for(key)
        partial = aside(path)
        partial.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with partial.open("wb") as stream:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLargeError(key)
                    stream.write(chunk)
            os.replace(partial, path)
        finally:
            partial.unlink(missing_ok=True)
        return size

    def existing_path(self, key: str) -> Path | None:
        """
        The file behind a key, if it exists (for serving downloads).

        :param key: The file.
        :type key: str
        :return: Its path, or None.
        :rtype: Path | None
        """
        path = self.path_for(key)
        return path if path.is_file() else None

    async def read(self, key: str) -> bytes | None:
        """
        Read a small file.

        :param key: The file.
        :type key: str
        :return: Its content, or None if absent.
        :rtype: bytes | None
        """
        path = self.existing_path(key)
        return (
            None if path is None else await asyncio.to_thread(path.read_bytes)
        )

    async def delete(self, key: str) -> None:
        """
        Remove a file; removing an absent file is fine.

        :param key: The file.
        :type key: str
        """
        self.path_for(key).unlink(missing_ok=True)

    async def list_names(self, folder: str) -> list[str]:
        """
        Names of the files directly inside a folder, skipping uploads
        still in progress (hidden ``.part`` files).

        :param folder: Key prefix such as ``uploads/<user>/<session>``.
        :type folder: str
        :return: File names, sorted; empty if there are none.
        :rtype: list[str]
        """
        directory = self.path_for(folder)
        if not directory.is_dir():
            return []
        return sorted(
            item.name
            for item in directory.iterdir()
            if item.is_file() and not item.name.startswith(".")
        )

    async def delete_folder(self, folder: str) -> None:
        """
        Remove every file under a key prefix; an absent one is fine.

        :param folder: Key prefix such as ``runs/<run>``.
        :type folder: str
        """
        await asyncio.to_thread(remove_tree, self.path_for(folder))


def remove_tree(path: Path) -> None:
    """
    Delete a folder and everything in it, if it exists.

    :param path: The folder.
    :type path: Path
    """
    shutil.rmtree(path, ignore_errors=True)


def aside(path: Path) -> Path:
    """
    A hidden, unique name next to ``path`` for writing before a rename.

    :param path: Final location.
    :type path: Path
    :return: Temporary location in the same folder (same disk, so the
        rename is atomic).
    :rtype: Path
    """
    return path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")


def write_atomically(path: Path, data: bytes) -> None:
    """
    Write ``data`` to ``path`` so it appears all at once.

    :param path: Final location.
    :type path: Path
    :param data: Content.
    :type data: bytes
    """
    partial = aside(path)
    partial.parent.mkdir(parents=True, exist_ok=True)
    try:
        partial.write_bytes(data)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
