"""
Zipping runs when the server asks (the house agent's runs always,
others on request): zip the run's folder, upload the zip, and report
how it went. Each zip is made in the background.
"""

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from typing import Protocol

import httpx

from agent.config import AgentConfig
from agent.packer import BundleTooLargeError, write_bundle
from agent.reporter import REPORT_RETRY_DELAYS
from agent.workspace import run_folder
from app.agents.schemas import BundleReport, PackOutcome, PackRequest

logger = logging.getLogger("agent")
# A server, or a proxy in front of it (a Cloudflare tunnel takes at
# most 100 MB per request), refusing a body this big.
PAYLOAD_TOO_LARGE = 413
FOLDER_GONE_MESSAGE = "The run's folder is not on this machine any more"


class BundleApi(Protocol):
    """
    The calls zipping a run makes; ``AgentClient`` or a test double.
    """

    async def upload_file(self, url: str, source: Path) -> None:
        """
        Stream a file to a signed upload link.

        :param url: Signed upload link.
        :type url: str
        :param source: File to send.
        :type source: Path
        """

    async def report_bundle(self, run_id, report: BundleReport) -> bool:
        """
        Report how zipping a run ended.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param report: Outcome.
        :type report: BundleReport
        :return: False if the server was not expecting it.
        :rtype: bool
        """


class Bundler:
    """
    Zips, uploads and reports runs, each at most once at a time.
    """

    def __init__(self, config: AgentConfig, client: BundleApi) -> None:
        """
        :param config: Agent settings (work folder; whether to delete a
            run's folder once uploaded).
        :type config: AgentConfig
        :param client: The API.
        :type client: BundleApi
        """
        self.config = config
        self.client = client
        # Runs being zipped, so a repeated request is not zipped twice.
        self.packing: set[uuid.UUID] = set()
        self.tasks: set[asyncio.Task] = set()

    def start(self, requests: list[PackRequest]) -> None:
        """
        Zip and upload each requested run in the background, skipping
        runs already being zipped.

        :param requests: Runs to zip.
        :type requests: list[PackRequest]
        """
        for request in requests:
            if request.run_id in self.packing:
                continue
            self.packing.add(request.run_id)
            task = asyncio.create_task(self.pack(request))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def close(self) -> None:
        """
        Stop zipping; the server's sweeper asks again for unfinished
        zips.
        """
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def pack(self, request: PackRequest) -> None:
        """
        Zip, upload and report one run. The run counts as being packed
        until its report is delivered: the server may ask for a slow
        zip again meanwhile, and on the house agent the folder is gone
        once uploaded, so packing it again could only fail.

        :param request: The run and where to upload it.
        :type request: PackRequest
        """
        try:
            outcome = await self.attempt(request)
            await self.deliver(request.run_id, outcome)
        finally:
            self.packing.discard(request.run_id)

    async def attempt(self, request: PackRequest) -> BundleReport:
        """
        Zip and upload one run; any failure becomes a "failed" report.

        :param request: The run and where to upload it.
        :type request: PackRequest
        :return: How packing ended.
        :rtype: BundleReport
        """
        try:
            return await self.build_and_upload(request)
        except Exception as error:  # outermost boundary of a background task
            logger.exception("Packing run %s failed", request.run_id)
            return BundleReport.failed(f"{type(error).__name__}: {error}")

    async def build_and_upload(self, request: PackRequest) -> BundleReport:
        """
        Zip the run's folder, upload the zip, and on the house agent
        remove the folder once uploaded.

        :param request: The run and where to upload it.
        :type request: PackRequest
        :return: Ready with its size, too big, or failed for a folder
            that is gone.
        :rtype: BundleReport
        :raises httpx.HTTPError: If the upload fails.
        """
        run_dir = run_folder(self.config.artifacts_dir, request.run_id)
        if not run_dir.is_dir():
            return BundleReport.failed(FOLDER_GONE_MESSAGE)
        report = await self.zip_and_upload(request, run_dir)
        ready = report.status == PackOutcome.READY
        if ready and self.config.delete_after_upload:
            await asyncio.to_thread(shutil.rmtree, run_dir, True)
        return report

    async def zip_and_upload(
        self, request: PackRequest, run_dir: Path
    ) -> BundleReport:
        """
        Zip a run's folder into a hidden file beside it and upload it;
        the zip is removed afterwards either way.

        :param request: The run and where to upload it.
        :type request: PackRequest
        :param run_dir: The run's folder.
        :type run_dir: Path
        :return: Ready with its size, or too big.
        :rtype: BundleReport
        :raises httpx.HTTPError: If the upload fails.
        """
        partial = run_dir.with_name(f".{run_dir.name}.zip.part")
        try:
            size = await asyncio.to_thread(
                write_bundle,
                run_dir,
                request.bundle_name,
                request.manifest,
                partial,
                request.max_bytes,
            )
            return await self.upload(request, partial, size)
        except BundleTooLargeError as error:
            return BundleReport.too_big(error.size_bytes)
        finally:
            partial.unlink(missing_ok=True)

    async def upload(
        self, request: PackRequest, partial: Path, size: int
    ) -> BundleReport:
        """
        Upload a finished zip. One refused for its size is "too big",
        not a failure: the run's folder is still there to copy.

        :param request: Where to upload it.
        :type request: PackRequest
        :param partial: The zip.
        :type partial: Path
        :param size: Its size in bytes.
        :type size: int
        :return: Ready, or too big.
        :rtype: BundleReport
        :raises httpx.HTTPError: For any other upload trouble.
        """
        try:
            await self.client.upload_file(request.upload_url, partial)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != PAYLOAD_TOO_LARGE:
                raise
            return BundleReport.too_big(size)
        return BundleReport.ready(size)

    async def deliver(self, run_id: uuid.UUID, outcome: BundleReport) -> None:
        """
        Report how packing ended, retrying through network trouble.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param outcome: How packing ended.
        :type outcome: BundleReport
        """
        for delay in REPORT_RETRY_DELAYS:
            try:
                if not await self.client.report_bundle(run_id, outcome):
                    logger.info("Server was not expecting run %s", run_id)
                return
            except httpx.HTTPError as error:
                logger.warning("Bundle report failed (%s); retrying", error)
                await asyncio.sleep(delay)
        logger.error("Gave up reporting the zip of run %s", run_id)
