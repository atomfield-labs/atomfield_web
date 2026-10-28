"""
The Bundler on its own (no agent around it): a run asked for twice
while its zip is being made is zipped, uploaded and reported once.
"""

import asyncio
import uuid
from pathlib import Path

import httpx

from agent.bundler import Bundler
from agent.config import AgentConfig
from agent.workspace import run_folder
from app.agents.schemas import BundleReport, PackRequest


class SlowUploads:
    """
    Stands in for the API: counts uploads, each taking a moment, and
    keeps the reports.
    """

    def __init__(self) -> None:
        """
        Nothing uploaded or reported yet.
        """
        self.uploads = 0
        self.reports: list[str] = []

    async def upload_file(self, url: str, source: Path) -> None:
        """
        Count one upload, slowly enough for a second request to arrive.

        :param url: Signed link (ignored).
        :type url: str
        :param source: The zip (ignored).
        :type source: Path
        """
        self.uploads += 1
        await asyncio.sleep(0.05)

    async def report_bundle(self, run_id, report: BundleReport) -> bool:
        """
        Keep how zipping ended.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param report: Outcome.
        :type report: BundleReport
        :return: Always expected.
        :rtype: bool
        """
        self.reports.append(report.status)
        return True


def test_a_run_asked_for_twice_is_zipped_once(tmp_path: Path):
    """
    The second request arrives while the first zip is uploading (as a
    heartbeat and a report can both carry it); it is ignored.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    run_id = uuid.uuid4()
    job_dir = run_folder(tmp_path, run_id) / "opt"
    job_dir.mkdir(parents=True)
    (job_dir / "opt.log").write_text("done\n")
    request = PackRequest(
        run_id=run_id,
        bundle_name="water_run",
        upload_url="/fake-store/bundle.zip",
        max_bytes=10_000_000,
        manifest={"run_id": str(run_id), "jobs": [{"node": "opt"}]},
    )
    client = SlowUploads()
    config = AgentConfig(
        api_url="http://unused", token="", artifacts_dir=tmp_path
    )
    bundler = Bundler(config, client)

    async def two_requests():
        bundler.start([request])
        bundler.start([request])
        await asyncio.gather(*bundler.tasks)

    asyncio.run(two_requests())
    assert (client.uploads, client.reports) == (1, ["ready"])


class SizeLimitedServer(SlowUploads):
    """
    Like a Cloudflare tunnel: refuses any upload bigger than its limit
    with 413 Payload Too Large.
    """

    async def upload_file(self, url: str, source: Path) -> None:
        """
        Refuse the zip, as a proxy would.

        :param url: Signed link.
        :type url: str
        :param source: The zip (ignored).
        :type source: Path
        :raises httpx.HTTPStatusError: Always, 413.
        """
        request = httpx.Request("PUT", "https://tunnel.example" + url)
        response = httpx.Response(413, request=request)
        raise httpx.HTTPStatusError("413", request=request, response=response)


def test_a_zip_refused_for_its_size_is_too_big_and_the_folder_stays(
    tmp_path: Path,
):
    """
    A 413 means "too big to upload here", reported as such with the
    zip's size; even on the house agent, the run's folder is kept.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    run_id = uuid.uuid4()
    job_dir = run_folder(tmp_path, run_id) / "opt"
    job_dir.mkdir(parents=True)
    (job_dir / "opt.log").write_text("done\n")
    request = PackRequest(
        run_id=run_id,
        bundle_name="water_run",
        upload_url="/fake-store/bundle.zip",
        max_bytes=10_000_000,
        manifest={"run_id": str(run_id), "jobs": [{"node": "opt"}]},
    )
    client = SizeLimitedServer()
    config = AgentConfig(
        api_url="http://unused",
        token="",
        artifacts_dir=tmp_path,
        delete_after_upload=True,
    )

    report = asyncio.run(Bundler(config, client).build_and_upload(request))

    assert report.status == "too_big"
    assert report.size_bytes and report.size_bytes > 0
    assert job_dir.is_dir()
