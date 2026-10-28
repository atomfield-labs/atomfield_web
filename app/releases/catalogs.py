"""
Which catalog applies: the newest release's for a new run, and each
run's own release's for its jobs, however many releases came since.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.catalog import Catalog
from app.catalog.models import CatalogDocument
from app.models.job import Job
from app.models.run import Run
from app.models.script_release import ScriptRelease
from app.releases.service import latest_release


@dataclass(frozen=True, slots=True)
class CurrentCatalog:
    """
    What a new run is checked against, and the release it is pinned to.

    :param release: The newest release; None before the first one.
    :type release: ScriptRelease | None
    :param catalog: Its catalog.
    :type catalog: Catalog
    """

    release: ScriptRelease | None
    catalog: Catalog

    @property
    def release_id(self) -> uuid.UUID | None:
        """
        The release's id, for the new run to remember.

        :return: Id, or None before the first release.
        :rtype: uuid.UUID | None
        """
        return self.release.id if self.release else None


class ReleaseCatalogs:
    """
    The catalog of each release, built the first time it is needed
    and kept for the life of the process. A release never changes, so
    its catalog can never go stale: nothing here is ever cleared.

    Runs from before the first release use the catalog file the server
    started with.
    """

    def __init__(self, unreleased: Catalog) -> None:
        """
        :param unreleased: Catalog for runs without a release.
        :type unreleased: Catalog
        """
        self.unreleased = unreleased
        self.built: dict[uuid.UUID, Catalog] = {}

    async def of_release(
        self, db: AsyncSession, release_id: uuid.UUID | None
    ) -> Catalog:
        """
        The catalog a run's jobs use.

        :param db: Asynchronous database session.
        :type db: AsyncSession
        :param release_id: The run's release.
        :type release_id: uuid.UUID | None
        :return: That release's catalog.
        :rtype: Catalog
        """
        if release_id is None:
            return self.unreleased
        if release_id not in self.built:
            release = await db.get(ScriptRelease, release_id)
            document = CatalogDocument.model_validate(release.catalog)
            self.built[release_id] = Catalog(document)
        return self.built[release_id]

    async def current(self, db: AsyncSession) -> CurrentCatalog:
        """
        The catalog a run submitted now is checked against.

        :param db: Asynchronous database session.
        :type db: AsyncSession
        :return: The newest release and its catalog.
        :rtype: CurrentCatalog
        """
        release = await latest_release(db)
        release_id = release.id if release else None
        return CurrentCatalog(release, await self.of_release(db, release_id))


async def run_data_packs(
    db: AsyncSession, catalogs: ReleaseCatalogs, run: Run
) -> list[str]:
    """
    The data packs a run's tasks read, from its release's catalog.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param catalogs: Catalogs by release.
    :type catalogs: ReleaseCatalogs
    :param run: The run.
    :type run: Run
    :return: ``name version`` of each pack, sorted.
    :rtype: list[str]
    """
    catalog = await catalogs.of_release(db, run.release_id)
    query = select(Job.script_name).where(Job.run_id == run.id).distinct()
    packs = set()
    for task_id in (await db.execute(query)).scalars():
        task = catalog.tasks.get(task_id)
        for need in task.data if task else ():
            packs.add(f"{need.name} {need.version}")
    return sorted(packs)
