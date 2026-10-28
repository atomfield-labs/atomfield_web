"""
Telling the server how a job ended: the outcome with the job's file
cards and folder, the small files the web UI shows, and delivery that
keeps trying through network trouble.
"""

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import httpx

from agent.config import AgentConfig
from agent.results import file_cards, pick_ui_files, upload_body
from app.agents.schemas import (
    CompletionRequest,
    CompletionResponse,
    FileCard,
    FolderLocation,
    JobAssignment,
    UploadLinksResponse,
)

logger = logging.getLogger("agent")
# Waits between attempts to deliver a result through network trouble.
REPORT_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)


class ResultsApi(Protocol):
    """
    The calls reporting a job makes; ``AgentClient`` or a test double.
    """

    async def upload_links(
        self,
        job_id,
        attempt: int,
        names: list[str],
    ) -> UploadLinksResponse | None:
        """
        Ask where to upload a finishing attempt's small files.

        :param job_id: The job.
        :type job_id: uuid.UUID
        :param attempt: Its attempt.
        :type attempt: int
        :param names: File names.
        :type names: list[str]
        :return: The links, or None if the attempt is stale.
        :rtype: UploadLinksResponse | None
        """

    async def upload(self, url: str, content: bytes) -> None:
        """
        Send bytes to a signed upload link.

        :param url: Signed upload link.
        :type url: str
        :param content: What to store.
        :type content: bytes
        """

    async def complete(
        self, job_id, report: CompletionRequest
    ) -> CompletionResponse | None:
        """
        Report how an attempt ended.

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Outcome.
        :type report: CompletionRequest
        :return: The server's reply, or None if refused as stale.
        :rtype: CompletionResponse | None
        """


class Reporter:
    """
    Builds and delivers the report of each finished job.
    """

    def __init__(self, config: AgentConfig, client: ResultsApi) -> None:
        """
        :param config: Agent settings (the address to copy files from).
        :type config: AgentConfig
        :param client: The API.
        :type client: ResultsApi
        """
        self.config = config
        self.client = client

    async def attach_results(
        self,
        assignment: JobAssignment,
        workspace: Path,
        report: CompletionRequest,
    ) -> CompletionRequest:
        """
        Add the job's file cards and folder location to its report,
        uploading the small files the UI shows. Trouble here is logged,
        never fatal: the job's outcome stands, and the files are still
        on this machine.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :param workspace: The job's folder.
        :type workspace: Path
        :param report: The outcome so far.
        :type report: CompletionRequest
        :return: The report with ``files`` and ``folder`` set.
        :rtype: CompletionRequest
        """
        folder = FolderLocation(
            path=str(workspace.parent), address=self.config.ssh_address
        )
        try:
            cards = await asyncio.to_thread(file_cards, workspace)
            uploaded = await self.upload_ui_files(assignment, workspace, cards)
        except (OSError, httpx.HTTPError) as error:
            logger.warning("Could not collect results (%s)", error)
            return report.model_copy(update={"folder": folder})
        cards = [
            card.model_copy(update={"uploaded": card.path in uploaded})
            for card in cards
        ]
        return report.model_copy(update={"files": cards, "folder": folder})

    async def upload_ui_files(
        self,
        assignment: JobAssignment,
        workspace: Path,
        cards: list[FileCard],
    ) -> set[str]:
        """
        Upload the small files the web UI shows.

        :param assignment: The attempt.
        :type assignment: JobAssignment
        :param workspace: The job's folder.
        :type workspace: Path
        :param cards: Every file of the job.
        :type cards: list[FileCard]
        :return: Names uploaded (none if the attempt went stale).
        :rtype: set[str]
        :raises httpx.HTTPError: On network trouble.
        """
        names = pick_ui_files(cards, assignment.task.id)
        grant = await self.client.upload_links(
            assignment.job_id, assignment.attempt, names
        )
        if not names or grant is None:
            return set()
        for name, url in grant.links.items():
            body = upload_body(workspace / name, grant.max_bytes)
            await self.client.upload(url, body)
        return set(grant.links)

    async def deliver(
        self,
        assignment: JobAssignment,
        report: CompletionRequest,
    ) -> CompletionResponse | None:
        """
        Deliver a result, retrying through network trouble. A 409 means
        the server already moved on (e.g. retried the job); that is
        final, not an error.

        :param assignment: The attempt being reported.
        :type assignment: JobAssignment
        :param report: The result.
        :type report: CompletionRequest
        :return: The server's reply; None if refused as stale or not
            delivered at all.
        :rtype: CompletionResponse | None
        """
        job_id = assignment.job_id
        for delay in REPORT_RETRY_DELAYS:
            try:
                recorded = await self.client.complete(job_id, report)
            except httpx.HTTPError as error:
                logger.warning("Report failed (%s); retrying", error)
                await asyncio.sleep(delay)
                continue
            if recorded is None:
                logger.info("Server refused stale report for %s", job_id)
            return recorded
        logger.error("Gave up reporting %s; its lease will expire", job_id)
        return None
