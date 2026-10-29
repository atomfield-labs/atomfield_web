"""
Publishing releases, and finding them again.

Publishing checks the wheel, stores it under its fingerprint, then
records it. The newest release is the one new runs are pinned to.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import ReleaseRef
from app.core.names import version_label
from app.models.script_release import ScriptRelease
from app.releases.data_packs import catalog_needs, missing_data_packs
from app.releases.published import already_published
from app.releases.wheel import (
    InvalidReleaseError,
    ReleaseContents,
    read_release,
)
from app.storage.keys import release_key
from app.storage.store import ArtifactStore

# Agents download a release right after claiming a job; an hour is
# ample.
RELEASE_LINK_SECONDS = 3600


async def latest_release(db: AsyncSession) -> ScriptRelease | None:
    """
    The release new runs use: the one published last.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The newest release, or None before the first.
    :rtype: ScriptRelease | None
    """
    query = (
        select(ScriptRelease)
        .order_by(ScriptRelease.published_at.desc())
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def find_release(
    db: AsyncSession, name: str, version: str
) -> ScriptRelease | None:
    """
    A release by name and version.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param name: Distribution name.
    :type name: str
    :param version: Version.
    :type version: str
    :return: The release, or None if it was never published.
    :rtype: ScriptRelease | None
    """
    query = select(ScriptRelease).where(
        ScriptRelease.name == name, ScriptRelease.version == version
    )
    return (await db.execute(query)).scalar_one_or_none()


async def publish_release(
    db: AsyncSession,
    store: ArtifactStore,
    data: bytes,
    git_commit: str | None = None,
) -> tuple[ScriptRelease, bool]:
    """
    Check a wheel and make it the newest release. Publishing the same
    file again changes nothing, so a publish can always be retried.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the wheel is kept.
    :type store: ArtifactStore
    :param data: The wheel file.
    :type data: bytes
    :param git_commit: The commit it was built from, if known.
    :type git_commit: str | None
    :return: The release, and whether it was new.
    :rtype: tuple[ScriptRelease, bool]
    :raises InvalidReleaseError: If agents could not run it, or a data
        pack it needs was never published.
    :raises PublishConflictError: If its version exists with other
        contents (a release never changes).
    """
    contents = read_release(data)
    await require_data_packs(db, contents)
    existing = await find_release(db, contents.name, contents.version)
    published = existing.sha256 if existing else None
    label = version_label(contents.name, contents.version)
    if already_published(published, contents.sha256, label):
        return existing, False
    # The file first: a failure before the commit leaves only a file
    # that nothing points to, which publishing it again rewrites.
    await store.write(release_key(contents.sha256), data)
    return await record_release(db, contents, git_commit), True


async def require_data_packs(
    db: AsyncSession, contents: ReleaseContents
) -> None:
    """
    Refuse a release whose tasks need a data pack that does not exist
    yet: its jobs could never start.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param contents: What the wheel holds.
    :type contents: ReleaseContents
    :raises InvalidReleaseError: Naming the missing packs.
    """
    missing = await missing_data_packs(db, catalog_needs(contents.catalog))
    if missing:
        raise InvalidReleaseError(
            f"Publish these data packs first: {', '.join(missing)}"
        )


async def record_release(
    db: AsyncSession,
    contents: ReleaseContents,
    git_commit: str | None,
) -> ScriptRelease:
    """
    Save a checked release; from now on it is the newest.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param contents: What the wheel holds.
    :type contents: ReleaseContents
    :param git_commit: The commit it was built from, if known.
    :type git_commit: str | None
    :return: The saved release.
    :rtype: ScriptRelease
    """
    release = ScriptRelease(
        name=contents.name,
        version=contents.version,
        sha256=contents.sha256,
        git_commit=git_commit,
        catalog=contents.catalog.model_dump(mode="json"),
    )
    db.add(release)
    await db.commit()
    await db.refresh(release)
    return release


async def release_ref(
    db: AsyncSession,
    store: ArtifactStore,
    release_id: uuid.UUID | None,
) -> ReleaseRef | None:
    """
    Tell an agent which release to run, with a link to download it.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Signs the link.
    :type store: ArtifactStore
    :param release_id: The run's release.
    :type release_id: uuid.UUID | None
    :return: The reference, or None for a run without a release.
    :rtype: ReleaseRef | None
    """
    if release_id is None:
        return None
    release = await db.get(ScriptRelease, release_id)
    link = store.download_link(
        release_key(release.sha256), RELEASE_LINK_SECONDS
    )
    return ReleaseRef(
        name=release.name,
        version=release.version,
        sha256=release.sha256,
        url=link,
    )


async def release_label(
    db: AsyncSession, release_id: uuid.UUID | None
) -> str | None:
    """
    How people see a run's release.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param release_id: The run's release.
    :type release_id: uuid.UUID | None
    :return: e.g. ``afscripts 0.2.0``, or None without a release.
    :rtype: str | None
    """
    if release_id is None:
        return None
    release = await db.get(ScriptRelease, release_id)
    return release.label
