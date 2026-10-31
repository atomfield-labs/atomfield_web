"""
Script releases on the server: a wheel is checked without running it,
each version is published once and never changes, and every run keeps
the release that was current when it was submitted.
"""

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.machines import ANY
from app.releases.bundle import InvalidReleaseError, read_release
from tests.fake_release import BUILT_FOR, FIXTURE_CATALOG, make_release
from tests.test_agent_api import (
    HOUSE,
    SHORT_WAIT,
    claim,
    complete,
    submit_chain,
)

CATALOG_FILE = "catalog.json"
CLAIMS = "/api/agent/claims"
SUBMIT = "/api/jobs/submit"
LINUX = "linux-x86_64"
MAC = "darwin-arm64"


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


def test_a_bundle_is_read_without_running_it():
    """
    Name, version, catalog and wheels come from the files inside; the
    fingerprint is the whole file's.
    """
    data = make_release("1.2.0")
    contents = read_release(data, may_hold_source=True)
    assert (contents.name, contents.version) == ("toy", "1.2.0")
    assert contents.sha256 == hashlib.sha256(data).hexdigest()
    task_ids = [task.id for task in contents.catalog.tasks]
    assert task_ids == ["toy_opt", "toy_network", "toy_solo"]
    assert {(wheel.package, wheel.machine) for wheel in contents.wheels} == {
        ("toy_chain", ANY),
        ("toy_other", ANY),
    }


ONLY_ONE_WHEEL = {
    "name": "toy",
    "version": "1.0.0",
    "wheels": [{"package": "toy_chain", "machine": ANY, "file": "x.whl"}],
}
GHOST_WHEEL = {
    **ONLY_ONE_WHEEL,
    "wheels": [
        {"package": "toy_chain", "machine": ANY, "file": "toy_chain-any.whl"},
        {"package": "toy_other", "machine": ANY, "file": "toy_other-any.whl"},
        {"package": "ghost", "machine": ANY, "file": "toy_other-any.whl"},
    ],
}
BAD_VERSION = {**ONLY_ONE_WHEEL, "version": "../x"}


@pytest.mark.parametrize(
    ("replace", "complaint"),
    [
        ({"catalog.json": None}, "no catalog.json"),
        ({"catalog.json": "{}"}, "catalog.json is invalid"),
        ({"release.json": None}, "no release.json"),
        ({"toy/network_driver.py": None}, "lacks: toy.network_driver"),
        ({"toy_chain-any.whl": None}, "no toy_chain-any.whl"),
        ({"toy_chain-any.whl": "not a zip"}, "not a zip"),
        ({"release.json": json.dumps(BAD_VERSION)}, "release.json is invalid"),
        ({"release.json": json.dumps(ONLY_ONE_WHEEL)}, "lacks wheels for"),
        ({"release.json": json.dumps(GHOST_WHEEL)}, "Wheels for no workflow"),
    ],
    ids=[
        "no-catalog",
        "bad-catalog",
        "no-manifest",
        "no-module",
        "no-wheel",
        "bad-wheel",
        "bad-version",
        "package-missing",
        "unknown-package",
    ],
)
def test_a_release_agents_could_not_run_is_refused(replace, complaint):
    """
    No catalog, a broken catalog, a task whose module is missing, a
    package without a wheel, a wheel for no package, a version that is
    a path: all refused.

    :param replace: Files changed in an otherwise good release.
    :type replace: dict[str, str | None]
    :param complaint: Part of the expected message.
    :type complaint: str
    """
    data = make_release(replace=replace)
    with pytest.raises(InvalidReleaseError, match=complaint):
        read_release(data, may_hold_source=True)
    with pytest.raises(InvalidReleaseError, match="not a zip"):
        read_release(b"just some bytes")


COMPILED_ONLY = {
    "toy/opt_driver.py": None,
    "toy/network_driver.py": None,
    "toy/solo_driver.py": None,
    "toy/opt_driver.abi3.so": "machine code",
    "toy/network_driver.abi3.so": "machine code",
    "toy/solo_driver.abi3.so": "machine code",
}


def test_source_code_is_refused_unless_tests_allow_it(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A release holding readable code is refused, naming the files, so
    source can never reach a server or a cluster by accident. Compiled
    modules and an empty ``__init__.py`` are fine.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param monkeypatch: Turns the tests' allowance off.
    :type monkeypatch: pytest.MonkeyPatch
    """
    with pytest.raises(InvalidReleaseError, match="toy/opt_driver.py"):
        read_release(make_release())
    compiled = make_release(replace=COMPILED_ONLY)
    assert read_release(compiled).version == "1.0.0"
    for readable in ("toy/__init__.py", "toy/opt_driver.c"):
        data = make_release(replace={**COMPILED_ONLY, readable: "x = 1\n"})
        with pytest.raises(InvalidReleaseError, match=readable):
            read_release(data)

    monkeypatch.setattr(settings, "RELEASES_MAY_HOLD_SOURCE", False)
    refused = client.post(
        "/api/releases", content=make_release(), headers=admin_headers
    )
    assert refused.status_code == 422
    assert "holds source code" in refused.json()["detail"]


def test_only_the_administrator_publishes_and_a_version_never_changes(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
):
    """
    Users may not publish. The same file again changes nothing, and so
    does a rebuild of the same commit (a publish can be retried); other
    contents under the same version are refused; an unusable file is
    refused.

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
    rebuilt = client.post(
        "/api/releases", content=changed, headers=admin_headers, params=commit
    )
    assert (rebuilt.status_code, rebuilt.json()["id"]) == (
        200,
        first.json()["id"],
    )
    found = client.get("/api/releases/toy/1.0.0")
    assert found.json()["id"] == first.json()["id"]
    assert client.get("/api/releases/toy/9.9.9").status_code == 404
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
    link to its wheel and that release's catalog; the editor and new
    runs get the newer release.

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


def claim_on(client: TestClient, machine: str | None):
    """
    Ask for a job as an agent on this kind of computer.

    :param client: In-process API client.
    :type client: TestClient
    :param machine: Its machine; None for an old agent.
    :type machine: str | None
    :return: HTTP response.
    :rtype: httpx.Response
    """
    body = {**SHORT_WAIT, "machine": machine}
    return client.post(CLAIMS, json=body, headers=HOUSE)


def built_for(client: TestClient, assignment: dict) -> str:
    """
    Which wheel an agent's link really gives.

    :param client: In-process API client.
    :type client: TestClient
    :param assignment: The agent's assignment.
    :type assignment: dict
    :return: Its package and machine.
    :rtype: str
    """
    wheel = client.get(assignment["release"]["url"]).content
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        return archive.read(BUILT_FOR).decode()


def test_a_job_gets_only_its_own_packages_file_for_its_machine(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
):
    """
    Each job's agent is sent one wheel: the job's package, built for
    that agent's kind of computer, so nothing else reaches it.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up the releases afterwards.
    :type releases: None
    """
    data = make_release("4.0.0", machines=(LINUX, MAC))
    client.post("/api/releases", content=data, headers=admin_headers)
    headers = make_user_headers()
    solo = {"script_name": "toy_solo", "parameters": {}}
    assert client.post(SUBMIT, json=solo, headers=headers).status_code == 202
    first = claim_on(client, LINUX).json()
    assert first["release"]["name"] == "toy-toy_other"
    assert built_for(client, first) == f"toy_other {LINUX}"

    submit_chain(client, headers)
    second = claim_on(client, MAC).json()
    assert second["release"]["name"] == "toy-toy_chain"
    assert built_for(client, second) == f"toy_chain {MAC}"


@pytest.mark.parametrize(
    ("machine", "message"),
    [
        ("linux-riscv64", "no toy_other build for linux-riscv64"),
        (None, "out of date"),
    ],
    ids=["no-build", "old-agent"],
)
def test_an_agent_with_no_build_fails_the_job_saying_why(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
    machine: str | None,
    message: str,
):
    """
    A job whose release has nothing for this computer fails at once,
    saying what to do, rather than waiting or running the wrong file.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up the releases afterwards.
    :type releases: None
    :param machine: The agent's machine.
    :type machine: str | None
    :param message: Part of the job's error.
    :type message: str
    """
    data = make_release("4.0.0", machines=(LINUX,))
    client.post("/api/releases", content=data, headers=admin_headers)
    headers = make_user_headers()
    solo = {"script_name": "toy_solo", "parameters": {}}
    job = client.post(SUBMIT, json=solo, headers=headers).json()
    assert claim_on(client, machine).status_code == 204
    failed = client.get(f"/api/jobs/{job['id']}", headers=headers).json()
    assert failed["status"] == "failed"
    assert message in failed["error_message"]
