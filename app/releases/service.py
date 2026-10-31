"""
Publishing releases, and finding them again.

Publishing checks the bundle, stores each wheel under its fingerprint,
then records them. The newest release is the one new runs are pinned to.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import ReleaseRef
from app.core.config import settings
from app.core.machines import ANY
from app.core.names import version_label
from app.models.script_release import ReleaseWheel, ScriptRelease
from app.releases.bundle import (
    InvalidReleaseError,
    ReleaseContents,
    WheelFile,
    read_release,
)
from app.releases.data_packs import catalog_needs, missing_data_packs
from app.releases.published import already_published
from app.storage.keys import release_key
from app.storage.store import ArtifactStore

# Agents download a release right after claiming a job; an hour is
# ample.
RELEASE_LINK_SECONDS = 3600
OLD_AGENT_MESSAGE = "This agent is out of date: copy it to this computer again."
NO_BUILD_MESSAGE = "{label} has no {package} build for {machine} computers."


class NoBuildError(Exception):
    """
    A release has no file a job's agent could run.
    """


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
    Check a bundle and make it the newest release. Publishing the same
    file, or a rebuild of the same commit, changes nothing, so a publish
    can always be retried.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Where the wheels are kept.
    :type store: ArtifactStore
    :param data: The bundle.
    :type data: bytes
    :param git_commit: The commit it was built from, if known.
    :type git_commit: str | None
    :return: The release, and whether it was new.
    :rtype: tuple[ScriptRelease, bool]
    :raises InvalidReleaseError: If agents could not run it, it holds
        source code, or a data pack it needs was never published.
    :raises PublishConflictError: If its version exists with other
        contents (a release never changes).
    """
    contents = read_release(data, settings.RELEASES_MAY_HOLD_SOURCE)
    await require_data_packs(db, contents)
    existing = await find_release(db, contents.name, contents.version)
    # A rebuild of one commit need not match byte for byte.
    if existing and git_commit and existing.git_commit == git_commit:
        return existing, False
    published = existing.sha256 if existing else None
    label = version_label(contents.name, contents.version)
    if already_published(published, contents.sha256, label):
        return existing, False
    # The files first: a failure before the commit leaves only files
    # that nothing points to, which publishing again rewrites.
    for wheel in contents.wheels:
        await store.write(release_key(wheel.sha256), wheel.data)
    return await record_release(db, contents, git_commit), True


async def require_data_packs(
    db: AsyncSession, contents: ReleaseContents
) -> None:
    """
    Refuse a release whose tasks need a data pack that does not exist
    yet: its jobs could never start.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param contents: What the bundle holds.
    :type contents: ReleaseContents
    :raises InvalidReleaseError: Naming the missing packs.
    """
    missing = await missing_data_packs(db, catalog_needs(contents.catalog))
    if missing:
        raise InvalidReleaseError(
            f"Publish these data packs first: {', '.join(missing)}"
        )


def wheel_row(release_id: uuid.UUID, wheel: WheelFile) -> ReleaseWheel:
    """
    The row saying a release has this wheel.

    :param release_id: The release.
    :type release_id: uuid.UUID
    :param wheel: The wheel.
    :type wheel: WheelFile
    :return: The row.
    :rtype: ReleaseWheel
    """
    return ReleaseWheel(
        release_id=release_id,
        package=wheel.package,
        machine=wheel.machine,
        sha256=wheel.sha256,
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
    :param contents: What the bundle holds.
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
    await db.flush()
    db.add_all(wheel_row(release.id, wheel) for wheel in contents.wheels)
    await db.commit()
    await db.refresh(release)
    return release


async def find_wheel(
    db: AsyncSession,
    release_id: uuid.UUID,
    package: str | None,
    machine: str | None,
) -> ReleaseWheel | None:
    """
    The file a job runs from: its package, built for its agent's
    machine. A release from before compiled packages has one file for
    all of them.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param release_id: The run's release.
    :type release_id: uuid.UUID
    :param package: The task's workflow; None without workflows.
    :type package: str | None
    :param machine: The agent's machine; None for an old agent.
    :type machine: str | None
    :return: The wheel, or None if there is none it could run.
    :rtype: ReleaseWheel | None
    """
    query = (
        select(ReleaseWheel)
        .where(
            ReleaseWheel.release_id == release_id,
            ReleaseWheel.package.in_([package or ANY, ANY]),
            ReleaseWheel.machine.in_([machine or ANY, ANY]),
        )
        .order_by(ReleaseWheel.package == ANY, ReleaseWheel.machine == ANY)
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def release_ref(
    db: AsyncSession,
    store: ArtifactStore,
    release_id: uuid.UUID | None,
    package: str | None,
    machine: str | None,
) -> ReleaseRef | None:
    """
    Tell an agent which file of a release to run, with a link to
    download it. It gets only the package this job needs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param store: Signs the link.
    :type store: ArtifactStore
    :param release_id: The run's release.
    :type release_id: uuid.UUID | None
    :param package: The task's workflow; None without workflows.
    :type package: str | None
    :param machine: The agent's machine; None for an old agent.
    :type machine: str | None
    :return: The reference, or None for a run without a release.
    :rtype: ReleaseRef | None
    :raises NoBuildError: If this release has none for that machine.
    """
    if release_id is None:
        return None
    release = await db.get(ScriptRelease, release_id)
    wheel = await find_wheel(db, release_id, package, machine)
    if wheel is None:
        raise NoBuildError(no_build_message(release, package, machine))
    link = store.download_link(release_key(wheel.sha256), RELEASE_LINK_SECONDS)
    named = wheel.package != ANY
    return ReleaseRef(
        name=f"{release.name}-{wheel.package}" if named else release.name,
        version=release.version,
        sha256=wheel.sha256,
        url=link,
    )


def no_build_message(
    release: ScriptRelease, package: str | None, machine: str | None
) -> str:
    """
    Why a job cannot start: its release was not built for this agent.

    :param release: The run's release.
    :type release: ScriptRelease
    :param package: The task's workflow.
    :type package: str | None
    :param machine: The agent's machine; None for an old agent.
    :type machine: str | None
    :return: The message.
    :rtype: str
    """
    if machine is None:
        return OLD_AGENT_MESSAGE
    return NO_BUILD_MESSAGE.format(
        label=release.label, package=package, machine=machine
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
