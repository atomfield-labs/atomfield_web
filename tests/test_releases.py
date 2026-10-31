"""
Script releases on the server: a wheel is checked without running it,
each version is published once and never changes, and every run keeps
the release that was current when it was submitted.
"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.releases.wheel import InvalidReleaseError, read_release
from tests.fake_release import FIXTURE_CATALOG, make_release
from tests.test_agent_api import claim, complete, submit_chain

CATALOG_FILE = "toy/catalog.json"


def publish(
    client: TestClient,
    headers: dict[str, str],
    version: str,
    title: str | None = None,
    **extra,
):
    """
    Upload a ``toy`` release.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Caller's key headers.
    :type headers: dict[str, str]
    :param version: The release's version.
    :type version: str
    :param title: A new title for ``toy_opt`` in its catalog.
    :type title: str | None
    :param extra: Request options, e.g. ``params``.
    :type extra: Any
    :return: HTTP response.
    :rtype: httpx.Response
    """
    replace = {CATALOG_FILE: retitled_catalog(title)} if title else None
    data = make_release(version, replace)
    return client.post("/api/releases", content=data, headers=headers, **extra)


def retitled_catalog(title: str) -> str:
    """
    The fixture catalog with ``toy_opt`` renamed, to tell catalogs of
    different releases apart.

    :param title: New title.
    :type title: str
    :return: Catalog JSON.
    :rtype: str
    """
    document = json.loads(FIXTURE_CATALOG.read_text())
    document["tasks"][0]["title"] = title
    return json.dumps(document)


def test_a_wheel_is_read_without_running_it():
    """
    Name, version and catalog come from the files inside; the
    fingerprint is the whole file's.
    """
    data = make_release("1.2.0")
    contents = read_release(data)
    assert (contents.name, contents.version) == ("toy", "1.2.0")
    assert contents.sha256 == hashlib.sha256(data).hexdigest()
    task_ids = [task.id for task in contents.catalog.tasks]
    assert task_ids == ["toy_opt", "toy_network"]


@pytest.mark.parametrize(
    ("replace", "complaint"),
    [
        ({"toy/catalog.json": None}, "no toy/catalog.json"),
        ({"toy/catalog.json": "{}"}, "catalog.json is invalid"),
        ({"toy/network_driver.py": None}, "lacks: toy.network_driver"),
        (
            {"toy-1.0.0.dist-info/WHEEL": "Root-Is-Purelib: false\n"},
            "pure Python",
        ),
        (
            {"toy-1.0.0.dist-info/METADATA": "Name: toy\nVersion: ../x\n"},
            "Unusable name or version",
        ),
    ],
)
def test_a_wheel_agents_could_not_run_is_refused(replace, complaint):
    """
    No catalog, a broken catalog, a task whose module is missing, a
    platform-specific wheel, a version that is a path: all refused.

    :param replace: Files changed in an otherwise good release.
    :type replace: dict[str, str | None]
    :param complaint: Part of the expected message.
    :type complaint: str
    """
    with pytest.raises(InvalidReleaseError, match=complaint):
        read_release(make_release(replace=replace))
    with pytest.raises(InvalidReleaseError, match="not a zip"):
        read_release(b"just some bytes")


def test_only_the_administrator_publishes_and_a_version_never_changes(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
):
    """
    Users may not publish. The same file again changes nothing (a
    publish can be retried); other contents under the same version are
    refused; an unusable file is refused.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up the releases afterwards.
    :type releases: None
    """
    assert publish(client, make_user_headers(), "1.0.0").status_code == 403
    commit = {"git_commit": "2e6d386"}
    first = publish(client, admin_headers, "1.0.0", params=commit)
    assert first.status_code == 201
    assert first.json()["git_commit"] == "2e6d386"
    again = publish(client, admin_headers, "1.0.0")
    assert (again.status_code, again.json()["id"]) == (200, first.json()["id"])

    changed = make_release(replace={"toy/__init__.py": "# changed\n"})
    response = client.post(
        "/api/releases", content=changed, headers=admin_headers
    )
    assert response.status_code == 409
    broken = client.post("/api/releases", content=b"x", headers=admin_headers)
    assert broken.status_code == 422
    assert client.get("/api/releases/current").json()["version"] == "1.0.0"


def test_a_run_keeps_its_release_when_a_newer_one_is_published(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
):
    """
    A run's every job gets the release current at submission, with a
    link to exactly that wheel and that release's catalog; the editor
    and new runs get the newer release.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up the releases afterwards.
    :type releases: None
    """
    publish(client, admin_headers, "1.0.0", title="Toy one")
    headers = make_user_headers()
    first, second = submit_chain(client, headers)
    publish(client, admin_headers, "2.0.0", title="Toy two")
    tasks = client.get("/api/task-definitions", headers=headers).json()
    assert tasks[0]["title"] == "Toy two"

    parent = claim(client).json()
    assert parent["release"]["version"] == "1.0.0"
    assert parent["task"]["title"] == "Toy one"
    wheel = client.get(parent["release"]["url"]).content
    assert hashlib.sha256(wheel).hexdigest() == parent["release"]["sha256"]
    assert complete(client, first, 1).status_code == 200
    child = claim(client).json()
    assert (child["job_id"], child["release"]["version"]) == (second, "1.0.0")
    assert child["task"]["title"] == "Toy one"

    submit_chain(client, headers)
    newer = claim(client).json()
    assert (newer["release"]["version"], newer["task"]["title"]) == (
        "2.0.0",
        "Toy two",
    )
