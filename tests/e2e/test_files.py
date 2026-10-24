"""
End-to-end checks of files against a running stack: inputs reach the
agent through signed links, logs come back through the store, and a
finished house run becomes a zip that downloads, with tampered links
refused. Run with ``pytest -m e2e``.
"""

import io
import time
import zipfile
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import requests

from tests.e2e.test_pipeline_execution import (
    BASE_URL,
    build_chain,
    create_user_headers,
    fetch_job,
    task_node,
)

pytestmark = pytest.mark.e2e

FINAL = {"succeeded", "failed", "upstream_failed", "cancelled"}
ZIP_DONE = {"ready", "too_big", "failed"}
TIMEOUT_SECONDS = 60


@pytest.fixture(scope="module")
def headers() -> dict[str, str]:
    """
    One user for the whole module: key creation is rate limited.

    :return: Headers carrying the user's key.
    :rtype: dict[str, str]
    """
    return create_user_headers("pytest_e2e_files")


def wait_for(check, what: str):
    """
    Call ``check`` until it returns something truthy.

    :param check: Returns a value, or something falsy to keep waiting.
    :type check: Callable[[], Any]
    :param what: What is awaited, for the failure message.
    :type what: str
    :return: The first truthy value.
    :rtype: Any
    """
    give_up_at = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < give_up_at:
        if value := check():
            return value
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture(scope="module")
def finished_run(headers: dict[str, str]) -> dict:
    """
    Run ``opt -> md`` on water to the end and wait for its zip.

    :param headers: User headers.
    :type headers: dict[str, str]
    :return: Submission receipt plus the zip's info.
    :rtype: dict
    """
    nodes = [task_node("opt", "xtb_opt"), task_node("md", "xtb_md", time=0.2)]
    receipt = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=build_chain(nodes, with_water=True),
        headers=headers,
    ).json()
    url = f"{BASE_URL}/api/runs/{receipt['run_id']}/bundle"

    def zip_settled():
        info = requests.get(url, headers=headers).json()
        return info if info["status"] in ZIP_DONE else None

    return {**receipt, "bundle": wait_for(zip_settled, "the run's zip")}


def test_logs_and_file_lists_come_back_through_the_store(
    headers: dict[str, str],
    finished_run: dict,
):
    """
    Each job's log is the copy its agent uploaded; its file list comes
    from the report and includes files in subfolders.

    :param headers: User headers.
    :type headers: dict[str, str]
    :param finished_run: The finished run.
    :type finished_run: dict
    """
    for node, job_id in finished_run["job_ids"].items():
        assert fetch_job(job_id, headers)["status"] == "succeeded", node
        info = requests.get(
            f"{BASE_URL}/api/jobs/{job_id}/logs", headers=headers
        ).json()
        assert "completed" in info["logs"].lower() or "saved" in info["logs"]
        assert "execution.log" in info["artifacts"]
    md = finished_run["job_ids"]["md"]
    md_files = requests.get(
        f"{BASE_URL}/api/jobs/{md}/logs", headers=headers
    ).json()["artifacts"]
    assert any("/" in path for path in md_files), md_files


def test_a_finished_house_run_downloads_as_one_zip(finished_run: dict):
    """
    The zip downloads through its signed link, under a readable name,
    with run.json and both node folders, and no upstream links.

    :param finished_run: The finished run.
    :type finished_run: dict
    """
    bundle = finished_run["bundle"]
    assert bundle["status"] == "ready"
    assert bundle["folder"] is None
    response = requests.get(BASE_URL + bundle["download_url"])
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    top = names[0].split("/")[0]
    assert f"{top}/run.json" in names
    assert any(name.startswith(f"{top}/opt/") for name in names)
    assert any(name.startswith(f"{top}/md/") for name in names)
    assert not any("/upstream/" in name for name in names)
    assert f'filename="{top}.zip"' in response.headers["content-disposition"]


def test_a_tampered_or_expired_link_is_refused(finished_run: dict):
    """
    Changing the signature, the file, or pushing the expiry later makes
    the server refuse the link with 403.

    :param finished_run: The finished run.
    :type finished_run: dict
    """
    link = finished_run["bundle"]["download_url"]
    parts = urlsplit(link)
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}

    def edited(path: str = parts.path, **changes: str) -> str:
        return f"{BASE_URL}{path}?{urlencode({**query, **changes})}"

    later = str(int(query["expires"]) + 3600)
    assert requests.get(edited(signature="0" * 64)).status_code == 403
    assert requests.get(edited(expires=later)).status_code == 403
    other = parts.path.replace("bundle.zip", "other.zip")
    assert requests.get(edited(other)).status_code == 403
    assert requests.get(edited(expires="1")).status_code == 403
