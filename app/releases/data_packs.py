"""
Data packs: zip files of data tasks read (pseudopotentials, model
weights), published once by the administrator and downloaded once per
machine by its agent.

A pack has a name and a version and never changes. Its upload is
written to the store as it arrives while its fingerprint is computed,
so a pack of hundreds of megabytes never has to fit in memory; it is
kept only if the fingerprint matches the one the publisher announced.
"""

import hashlib
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import DataRef
from app.catalog.models import CatalogDocument, DataNeed
from app.core.names import version_label
from app.models.data_pack import DataPack
from app.releases.published import already_published
from app.storage.keys import data_pack_key
from app.storage.store import ArtifactStore

MAX_DATA_PACK_BYTES = 1024**3
# Agents download packs right after claiming a job.
DATA_LINK_SECONDS = 3600
# Every zip file made by ``zipfile`` (or ``zip``) starts with these.
ZIP_MAGIC = b"PK\x03\x04"
NOT_ANNOUNCED_MESSAGE = (
    "The upload is not a zip file with the announced fingerprint"
)


class InvalidDataPackError(ValueError):
    """
    The upload is not the zip file the publisher described.
    """


@dataclass(frozen=True, slots=True)
class DataPackUpload:
    """
    What the publisher says it is uploading.

    :param name: The pack's name, e.g. ``pslibrary-rel-pbe``.
    :type name: str
    :param version: Its version.
    :type version: str
    :param sha256: Fingerprint of the zip, in hex.
    :type sha256: str
    """

    name: str
    version: str
    sha256: str

    @property
    def label(self) -> str:
        """
        How people see the pack.

        :return: Its name and version.
        :rtype: str
        """
        return version_label(self.name, self.version)


class Fingerprint:
    """
    Watches bytes stream past: their sha256, and how they began.
    """

    def __init__(self) -> None:
        """
        Nothing seen yet.
        """
        self.digest = hashlib.sha256()
        self.head = b""

    async def watch(self, chunks: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
        """
        Pass chunks through unchanged, noting each one.

        :param chunks: The upload.
        :type chunks: AsyncIterable[bytes]
        :return: The same chunks.
        :rtype: AsyncIterator[bytes]
        """
        async for chunk in chunks:
            self.digest.update(chunk)
            self.head = (self.head + chunk[: len(ZIP_MAGIC)])[: len(ZIP_MAGIC)]
            yield chunk

    def matches(self, sha256: str) -> bool:
        """
        Whether the bytes seen are a zip file with this fingerprint.

        :param sha256: The announced fingerprint.
        :type sha256: str
        :return: True if both hold.
        :rtype: bool
        """
        return self.head == ZIP_MAGIC and self.digest.hexdigest() == sha256


async def find_data_pack(
    db: AsyncSession, name: str, version: str
) -> DataPack | None:
    """
    A data pack by name and version.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param name: The pack's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :return: The pack, or None if it was never published.
    :rtype: DataPack | None
    """
    query = select(DataPack).where(
        DataPack.name == name, DataPack.version == version
    )
    return (await db.execute(query)).scalar_one_or_none()


async def list_data_packs(db: AsyncSession) -> list[DataPack]:
    """
    Every published data pack, by name then version.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The packs.
    :rtype: list[DataPack]
    """
    query = select(DataPack).order_by(DataPack.name, DataPack.version)
    return list((await db.execute(query)).scalars())


async def publish_data_pack(
    db: AsyncSession,
    store: ArtifactStore,
    upload: DataPackUpload,
    chunks: AsyncIterable[bytes],
) -> tuple[DataPack, bool]:
    """
    Store an uploaded zip and record it, if it is what was announced.
    Publishing the same pack again changes nothing (and reads nothing).

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the zip is kept.
    :type store: ArtifactStore
    :param upload: Name, version and fingerprint, as announced.
    :type upload: DataPackUpload
    :param chunks: The zip's bytes.
    :type chunks: AsyncIterable[bytes]
    :return: The pack, and whether it is new.
    :rtype: tuple[DataPack, bool]
    :raises PublishConflictError: If the version exists with other
        contents.
    :raises InvalidDataPackError: If the bytes are not that zip.
    :raises TooLargeError: Past ``MAX_DATA_PACK_BYTES``.
    """
    existing = await find_data_pack(db, upload.name, upload.version)
    published = existing.sha256 if existing else None
    if already_published(published, upload.sha256, upload.label):
        return existing, False
    size = await store_checked(store, upload, chunks)
    return await record_data_pack(db, upload, size), True


async def store_checked(
    store: ArtifactStore,
    upload: DataPackUpload,
    chunks: AsyncIterable[bytes],
) -> int:
    """
    Store an upload as it arrives while fingerprinting it, and keep it
    only if it is the zip that was announced.

    :param store: Where the zip is kept.
    :type store: ArtifactStore
    :param upload: Name, version and fingerprint, as announced.
    :type upload: DataPackUpload
    :param chunks: The zip's bytes.
    :type chunks: AsyncIterable[bytes]
    :return: Its size in bytes.
    :rtype: int
    :raises InvalidDataPackError: If the bytes are not that zip.
    :raises TooLargeError: Past ``MAX_DATA_PACK_BYTES``.
    """
    key = data_pack_key(upload.name, upload.version)
    fingerprint = Fingerprint()
    watched = fingerprint.watch(chunks)
    size = await store.save_stream(key, watched, MAX_DATA_PACK_BYTES)
    if not fingerprint.matches(upload.sha256):
        await store.delete(key)
        raise InvalidDataPackError(NOT_ANNOUNCED_MESSAGE)
    return size


async def record_data_pack(
    db: AsyncSession, upload: DataPackUpload, size: int
) -> DataPack:
    """
    Save a checked pack.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param upload: Name, version and fingerprint.
    :type upload: DataPackUpload
    :param size: Its size in bytes.
    :type size: int
    :return: The saved pack.
    :rtype: DataPack
    """
    pack = DataPack(
        name=upload.name,
        version=upload.version,
        sha256=upload.sha256,
        size_bytes=size,
    )
    db.add(pack)
    await db.commit()
    await db.refresh(pack)
    return pack


async def missing_data_packs(
    db: AsyncSession, needs: list[DataNeed]
) -> list[str]:
    """
    The needed packs that were never published.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param needs: Packs some tasks read.
    :type needs: list[DataNeed]
    :return: ``name version`` of each missing one, sorted.
    :rtype: list[str]
    """
    missing = set()
    for need in needs:
        if await find_data_pack(db, need.name, need.version) is None:
            missing.add(version_label(need.name, need.version))
    return sorted(missing)


def catalog_needs(catalog: CatalogDocument) -> list[DataNeed]:
    """
    Every data pack any task of a catalog reads.

    :param catalog: The catalog.
    :type catalog: CatalogDocument
    :return: The needs, task by task.
    :rtype: list[DataNeed]
    """
    return [need for task in catalog.tasks for need in task.data]


async def data_refs(
    db: AsyncSession,
    store: ArtifactStore,
    needs: list[DataNeed],
) -> list[DataRef]:
    """
    Tell an agent which data packs a job needs, with download links.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Signs the links.
    :type store: ArtifactStore
    :param needs: The task's needs; each pack must exist.
    :type needs: list[DataNeed]
    :return: One reference per need.
    :rtype: list[DataRef]
    """
    refs = []
    for need in needs:
        pack = await find_data_pack(db, need.name, need.version)
        key = data_pack_key(pack.name, pack.version)
        refs.append(
            DataRef(
                name=pack.name,
                version=pack.version,
                sha256=pack.sha256,
                url=store.download_link(key, DATA_LINK_SECONDS),
                env=need.env,
            )
        )
    return refs
