"""
The Bundler on its own (no agent around it): a run asked for twice
while its zip is being made, or reported, is zipped, uploaded and
reported once.
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


class SlowReports(SlowUploads):
    """
    Takes a moment to accept each report, as over a slow network, and
    says when one is on its way.
    """

    def __init__(self) -> None:
        """
        Nothing uploaded or reported yet.
        """
        super().__init__()
        self.reporting = asyncio.Event()

    async def report_bundle(self, run_id, report: BundleReport) -> bool:
        """
        Keep how zipping ended, after a moment.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param report: Outcome.
        :type report: BundleReport
        :return: Always expected.
        :rtype: bool
        """
        self.reporting.set()
        await asyncio.sleep(0.05)
        return await super().report_bundle(run_id, report)


def packed_run(tmp_path: Path) -> PackRequest:
    """
    A finished run's folder holding one job's log, and the request to
    zip it.

    :param tmp_path: The agent's work folder.
    :type tmp_path: Path
    :return: The request.
    :rtype: PackRequest
    """
    run_id = uuid.uuid4()
    job_dir = run_folder(tmp_path, run_id) / "opt"
    job_dir.mkdir(parents=True)
    (job_dir / "opt.log").write_text("done\n")
    return PackRequest(
        run_id=run_id,
        bundle_name="water_run",
        upload_url="/fake-store/bundle.zip",
        max_bytes=10_000_000,
        manifest={"run_id": str(run_id), "jobs": [{"node": "opt"}]},
    )


def bundler_for(
    tmp_path: Path, client: SlowUploads, **settings: bool
) -> Bundler:
    """
    A Bundler working in ``tmp_path`` against a stand-in API.

    :param tmp_path: The agent's work folder.
    :type tmp_path: Path
    :param client: The stand-in API.
    :type client: SlowUploads
    :param settings: Other agent settings, e.g. ``delete_after_upload``.
    :type settings: bool
    :return: The Bundler.
    :rtype: Bundler
    """
    config = AgentConfig(
        api_url="http://unused", token="", artifacts_dir=tmp_path, **settings
    )
    return Bundler(config, client)


def test_a_run_asked_for_twice_is_zipped_once(tmp_path: Path):
    """
    The second request arrives while the first zip is uploading (as a
    heartbeat and a report can both carry it); it is ignored.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    request = packed_run(tmp_path)
    client = SlowUploads()
    bundler = bundler_for(tmp_path, client)

    async def two_requests() -> None:
        """
        Ask for the run twice in a row.
        """
        bundler.start([request])
        bundler.start([request])
        await asyncio.gather(*bundler.tasks)

    asyncio.run(two_requests())
    assert (client.uploads, client.reports) == (1, ["ready"])


def test_a_run_asked_for_while_its_report_is_sent_is_not_zipped_again(
    tmp_path: Path,
):
    """
    The zip is uploaded and its report on its way when the request
    comes again (the sweeper asks again for a slow zip). The run still
    counts as being packed until the report is delivered, so it is not
    zipped a second time.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    request = packed_run(tmp_path)
    client = SlowReports()
    bundler = bundler_for(tmp_path, client)

    async def ask_again_while_reporting() -> None:
        """
        Ask for the run, then again once its report is on its way.
        """
        bundler.start([request])
        await client.reporting.wait()
        bundler.start([request])
        await asyncio.gather(*bundler.tasks)

    asyncio.run(ask_again_while_reporting())
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
    request = packed_run(tmp_path)
    client = SizeLimitedServer()
    bundler = bundler_for(tmp_path, client, delete_after_upload=True)

    report = asyncio.run(bundler.build_and_upload(request))

    assert report.status == "too_big"
    assert report.size_bytes and report.size_bytes > 0
    assert run_folder(tmp_path, request.run_id).is_dir()
