"""
What the agent downloads once and keeps: each archive (a scripts
release or a data pack) is fetched once and checked against its
fingerprint; a job runs the scripts of its release and finds its data
packs in their variables; an owner's own copy wins; a job with no
scripts at all fails with a clear message.
"""

import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from agent.archives import ArchiveCache, ArchiveMismatchError, folder_name
from agent.made_with import MADE_WITH_NOTE
from agent.workspace import run_folder
from app.agents.schemas import DataRef, ReleaseRef
from tests.fake_release import make_wheel
from tests.test_agent import FakeClient, assign, make_agent, run_until

WHEEL = make_wheel()
RELEASE_URL = "/fake-store/releases/toy-1.0.0.whl"
RELEASE = ReleaseRef(
    name="toy",
    version="1.0.0",
    sha256=hashlib.sha256(WHEEL).hexdigest(),
    url=RELEASE_URL,
)
TABLE = "Fe Fe.rel-pbe-n-kjpaw_psl.1.0.0.UPF\n"
DATA_URL = "/fake-store/data/toy-data/1.zip"


def zipped(files: dict[str, str]) -> bytes:
    """
    A zip file holding the given files.

    :param files: Name -> content.
    :type files: dict[str, str]
    :return: The zip's bytes.
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


DATA_ZIP = zipped({"table.txt": TABLE})
DATA = DataRef(
    name="toy-data",
    version="1",
    sha256=hashlib.sha256(DATA_ZIP).hexdigest(),
    url=DATA_URL,
    env="TOY_DATA",
)


def read_note(tmp_path: Path, job) -> dict:
    """
    The ``.af_made_with`` note of a finished job.

    :param tmp_path: The agent's test folder.
    :type tmp_path: Path
    :param job: The job's assignment.
    :type job: JobAssignment
    :return: The note.
    :rtype: dict
    """
    folder = run_folder(tmp_path / "jobs", job.run_id) / job.node_key
    return json.loads((folder / MADE_WITH_NOTE).read_text())


def test_an_archive_is_downloaded_once_and_checked(tmp_path: Path):
    """
    Two jobs asking at the same moment share one download; later jobs
    find the archive in place; nothing half-done is left behind.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    downloads = []

    async def slow_download(url: str, destination: Path) -> None:
        downloads.append(url)
        await asyncio.sleep(0.05)
        destination.write_bytes(WHEEL)

    cache = ArchiveCache(tmp_path / "releases", slow_download)

    async def three_jobs():
        both = await asyncio.gather(
            cache.ensure(RELEASE), cache.ensure(RELEASE)
        )
        return [*both, await cache.ensure(RELEASE)]

    folders = asyncio.run(three_jobs())
    assert folders == [cache.folder(RELEASE)] * 3
    assert (folders[0] / "toy" / "opt_driver.py").is_file()
    assert downloads == [RELEASE_URL]
    leftovers = [path.name for path in (tmp_path / "releases").iterdir()]
    assert leftovers == [folder_name(RELEASE)]


def test_an_archive_that_does_not_match_its_fingerprint_is_not_used(
    tmp_path: Path,
):
    """
    A download whose fingerprint differs from the server's is thrown
    away, not unpacked.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """

    async def tampered_download(url: str, destination: Path) -> None:
        destination.write_bytes(WHEEL + b"tampered")

    cache = ArchiveCache(tmp_path / "releases", tampered_download)
    with pytest.raises(ArchiveMismatchError, match="fingerprint"):
        asyncio.run(cache.ensure(RELEASE))
    assert list((tmp_path / "releases").iterdir()) == []


def test_a_job_runs_its_release_and_finds_its_data_pack(tmp_path: Path):
    """
    Without an own copy, the job's scripts come from its release (the
    only place the ``toy`` package exists); its data pack is unpacked
    and named in its variable; its folder notes both.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1).model_copy(
        update={"release": RELEASE, "data": [DATA]}
    )
    client = FakeClient(job)
    client.served.update({RELEASE_URL: WHEEL, DATA_URL: DATA_ZIP})
    agent = make_agent(tmp_path, client, own_copy=False)
    run_until(agent, lambda: client.reports)

    assert client.reports[job.job_id].outcome == "succeeded"
    folder = run_folder(tmp_path / "jobs", job.run_id) / job.node_key
    assert (folder / "data_used.txt").read_text() == TABLE
    note = read_note(tmp_path, job)
    assert note["scripts"]["version"] == "1.0.0"
    assert note["scripts"]["sha256"] == RELEASE.sha256
    assert Path(note["scripts"]["folder"]).name == folder_name(RELEASE)
    assert [pack["env"] for pack in note["data"]] == ["TOY_DATA"]
    assert Path(note["data"][0]["folder"]).name == folder_name(DATA)


def test_an_own_copy_wins_and_without_either_a_job_fails(tmp_path: Path):
    """
    An owner's own copy runs instead of the release (nothing is
    downloaded); with no release and no own copy, the job fails saying
    why.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    job = assign(charge=1).model_copy(update={"release": RELEASE})
    client = FakeClient(job)
    run_until(make_agent(tmp_path / "own", client), lambda: client.reports)
    assert client.reports[job.job_id].outcome == "succeeded"
    assert RELEASE_URL not in client.downloads
    note = read_note(tmp_path / "own", job)
    assert note["scripts"]["source"] == "own copy"

    bare = assign()
    client = FakeClient(bare)
    agent = make_agent(tmp_path / "bare", client, own_copy=False)
    run_until(agent, lambda: client.reports)
    report = client.reports[bare.job_id]
    assert report.outcome == "failed"
    assert "no scripts release" in report.error_message
