"""
Zip files the agent downloads once and keeps: scripts releases (in
``<work>/releases/``) and data packs (in ``<work>/data/``).

Each archive is downloaded, checked against its fingerprint, unzipped
into a temporary folder beside its final place, then renamed into
place. A rename happens all at once, so a job sees the whole archive
or none of it, never half. Archives stay side by side: a three-day job
keeps its files while newer jobs use newer ones.
"""

import asyncio
import hashlib
import shutil
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path

from agent.workspace import require_plain_name
from app.agents.schemas import ArchiveRef

INCOMING_PREFIX = ".incoming-"
HASH_CHUNK_BYTES = 1024 * 1024
Download = Callable[[str, Path], Awaitable[None]]


class ArchiveMismatchError(RuntimeError):
    """
    A downloaded archive does not match its fingerprint.
    """


class ArchiveUnavailableError(RuntimeError):
    """
    An archive could not be downloaded.
    """

    def __init__(self, archive: ArchiveRef, error: Exception) -> None:
        """
        :param archive: The archive.
        :type archive: ArchiveRef
        :param error: Why the download failed.
        :type error: Exception
        """
        super().__init__(
            f"Could not download {archive.name} {archive.version}: {error}"
        )


def folder_name(archive: ArchiveRef) -> str:
    """
    Name of an archive's folder: readable, and different for any
    different content (``afscripts-0.2.0-8401db96c30f``).

    :param archive: The archive.
    :type archive: ArchiveRef
    :return: A plain folder name.
    :rtype: str
    :raises ValueError: If the server sent a name that is a path.
    """
    short = archive.sha256[:12]
    return require_plain_name(f"{archive.name}-{archive.version}-{short}")


def file_sha256(path: Path) -> str:
    """
    The fingerprint of a file.

    :param path: The file.
    :type path: Path
    :return: Its sha256, in hex.
    :rtype: str
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def unpack(source: Path, incoming: Path, folder: Path) -> None:
    """
    Unzip into ``incoming``, then rename that to ``folder``. If another
    process installed the same archive first, keep theirs.

    :param source: The checked zip file.
    :type source: Path
    :param incoming: Temporary folder beside ``folder``.
    :type incoming: Path
    :param folder: Where the archive belongs.
    :type folder: Path
    """
    with zipfile.ZipFile(source) as archive:
        archive.extractall(incoming)
    try:
        incoming.rename(folder)
    except OSError:
        if not folder.is_dir():
            raise
        shutil.rmtree(incoming)


class ArchiveCache:
    """
    Archives unpacked under one folder, each downloaded only once,
    even when several jobs ask for it at the same moment.
    """

    def __init__(self, root: Path, download: Download) -> None:
        """
        :param root: Folder holding the archives.
        :type root: Path
        :param download: Saves what a signed link serves to a file.
        :type download: Download
        """
        self.root = root
        self.download = download
        # One lock per archive: the second job waits for the first
        # one's download instead of starting its own.
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def folder(self, archive: ArchiveRef) -> Path:
        """
        Where an archive is (or will be) unpacked.

        :param archive: The archive.
        :type archive: ArchiveRef
        :return: Its folder.
        :rtype: Path
        """
        return self.root / folder_name(archive)

    async def ensure(self, archive: ArchiveRef) -> Path:
        """
        The archive's folder, downloading it first if needed.

        :param archive: The archive.
        :type archive: ArchiveRef
        :return: Its folder, complete.
        :rtype: Path
        :raises ArchiveMismatchError: If the download is not the
            archive the server described.
        :raises httpx.HTTPError: If it cannot be downloaded.
        """
        folder = self.folder(archive)
        async with self.locks[folder.name]:
            if not folder.is_dir():
                await self.install(archive, folder)
        return folder

    async def install(self, archive: ArchiveRef, folder: Path) -> None:
        """
        Download, check and unpack one archive.

        :param archive: The archive.
        :type archive: ArchiveRef
        :param folder: Where it belongs.
        :type folder: Path
        :raises ArchiveMismatchError: If its fingerprint is wrong.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        incoming = self.root / f"{INCOMING_PREFIX}{uuid.uuid4().hex}"
        download = incoming.with_name(f"{incoming.name}.zip")
        try:
            await self.download(archive.url, download)
            if file_sha256(download) != archive.sha256:
                raise ArchiveMismatchError(
                    f"{archive.name} {archive.version} does not match "
                    "its fingerprint; not using it"
                )
            await asyncio.to_thread(unpack, download, incoming, folder)
        finally:
            download.unlink(missing_ok=True)
            shutil.rmtree(incoming, ignore_errors=True)
