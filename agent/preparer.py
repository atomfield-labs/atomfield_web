"""
Getting a job ready to start: its scripts (a release, or the owner's
own copy), its data packs, its folder with the input files, and the
command that runs it.
"""

from dataclasses import dataclass
from pathlib import Path

import httpx

from agent.archives import ArchiveCache, ArchiveUnavailableError, Download
from agent.config import AgentConfig
from agent.made_with import scripts_entry, write_made_with
from agent.runner import Command
from agent.workspace import (
    DATA_DIR,
    EXECUTION_LOG,
    RELEASES_DIR,
    job_environment,
    prepare_workspace,
    require_plain_name,
)
from app.agents.schemas import ArchiveRef, JobAssignment, ReleaseRef
from app.catalog.argv import Invocation, build_argv


class NoScriptsError(RuntimeError):
    """
    A job without a release, on an agent without its own copy.
    """


class InputUnavailableError(RuntimeError):
    """
    An input file could not be downloaded.
    """

    def __init__(self, name: str, error: httpx.HTTPError) -> None:
        """
        :param name: The file.
        :type name: str
        :param error: Why the download failed.
        :type error: httpx.HTTPError
        """
        super().__init__(f"Could not download input {name!r}: {error}")


@dataclass(frozen=True, slots=True)
class PreparedJob:
    """
    A job ready to start.

    :param workspace: Its folder, with its inputs.
    :type workspace: Path
    :param command: What the runner starts.
    :type command: Command
    """

    workspace: Path
    command: Command


def invocation_for(assignment: JobAssignment) -> Invocation:
    """
    Describe one run of an assigned job for ``build_argv``.

    :param assignment: What the server handed out.
    :type assignment: JobAssignment
    :return: Values, inputs and platform-filled values.
    :rtype: Invocation
    """
    return Invocation(
        values=assignment.parameters,
        inputs=assignment.input_files,
        job_name=assignment.task.id,
        cpus=assignment.task.resources.cpus,
    )


async def fetch_archive(cache: ArchiveCache, archive: ArchiveRef) -> Path:
    """
    An archive's folder, downloaded the first time it is needed.

    :param cache: Where archives of this kind are kept.
    :type cache: ArchiveCache
    :param archive: The release or data pack.
    :type archive: ArchiveRef
    :return: Its folder.
    :rtype: Path
    :raises ArchiveUnavailableError: If the download fails.
    :raises ArchiveMismatchError: If the download is not that archive.
    """
    try:
        return await cache.ensure(archive)
    except httpx.HTTPError as error:
        raise ArchiveUnavailableError(archive, error) from error


class Preparer:
    """
    Puts everything a job needs in place before it starts.
    """

    def __init__(self, config: AgentConfig, download: Download) -> None:
        """
        :param config: Agent settings.
        :type config: AgentConfig
        :param download: Saves what a signed link serves to a file.
        :type download: Download
        """
        self.config = config
        self.download = download
        work = config.artifacts_dir
        self.releases = ArchiveCache(work / RELEASES_DIR, download)
        self.data = ArchiveCache(work / DATA_DIR, download)

    async def prepare(self, assignment: JobAssignment) -> PreparedJob:
        """
        Scripts, data packs, the job's folder and its inputs, then the
        command.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :return: The job's folder, and its command.
        :rtype: PreparedJob
        """
        scripts = await self.scripts_folder(assignment)
        data = await self.data_folders(assignment)
        workspace = prepare_workspace(self.config.artifacts_dir, assignment)
        used = scripts_entry(scripts, self.release_used(assignment))
        write_made_with(workspace, used, assignment.data, data)
        await self.fetch_inputs(assignment, workspace)
        command = self.command_for(assignment, workspace, scripts, data)
        return PreparedJob(workspace, command)

    def release_used(self, assignment: JobAssignment) -> ReleaseRef | None:
        """
        The release a job runs: its run's, unless the owner chose to
        run their own copy (``pack_dir``).

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :return: The release, or None for the owner's own copy.
        :rtype: ReleaseRef | None
        """
        if self.config.pack_source_dir is not None:
            return None
        return assignment.release

    async def scripts_folder(self, assignment: JobAssignment) -> Path:
        """
        Where the job's scripts are: the owner's own copy if they chose
        one, else the job's release, downloaded the first time.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :return: Folder to put on ``PYTHONPATH``.
        :rtype: Path
        :raises NoScriptsError: Without a release or an own copy.
        :raises ArchiveUnavailableError: If the download fails.
        """
        if self.config.pack_source_dir is not None:
            return self.config.pack_source_dir
        if assignment.release is None:
            raise NoScriptsError(
                "This run has no scripts release and this agent has no "
                "copy of its own (pack_dir): publish a release"
            )
        return await fetch_archive(self.releases, assignment.release)

    async def data_folders(self, assignment: JobAssignment) -> dict[str, Path]:
        """
        Have each data pack the job reads in place.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :return: Environment variable -> the pack's folder.
        :rtype: dict[str, Path]
        :raises ArchiveUnavailableError: If a download fails.
        """
        folders = {}
        for pack in assignment.data:
            folders[pack.env] = await fetch_archive(self.data, pack)
        return folders

    async def fetch_inputs(
        self,
        assignment: JobAssignment,
        workspace: Path,
    ) -> None:
        """
        Download each input file into the job's folder.

        :param assignment: The attempt and its input links.
        :type assignment: JobAssignment
        :param workspace: The job's folder.
        :type workspace: Path
        :raises InputUnavailableError: If a file cannot be downloaded;
            the job then fails with that message.
        """
        for item in assignment.inputs:
            destination = workspace / require_plain_name(item.name)
            try:
                await self.download(item.url, destination)
            except httpx.HTTPError as error:
                raise InputUnavailableError(item.name, error) from error

    def command_for(
        self,
        assignment: JobAssignment,
        workspace: Path,
        scripts: Path,
        data: dict[str, Path],
    ) -> Command:
        """
        The command that runs one attempt.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :param workspace: The job's folder.
        :type workspace: Path
        :param scripts: Folder holding the scripts.
        :type scripts: Path
        :param data: Environment variable -> data pack folder.
        :type data: dict[str, Path]
        :return: Command for the runner.
        :rtype: Command
        """
        argv = build_argv(
            assignment.task, invocation_for(assignment), self.config.python_bin
        )
        packs = {variable: str(folder) for variable, folder in data.items()}
        return Command(
            argv=argv,
            workspace=workspace,
            log_path=workspace / EXECUTION_LOG,
            environment={**job_environment(scripts), **packs},
            name=f"af-{assignment.node_key}",
            resources=assignment.task.resources,
        )
