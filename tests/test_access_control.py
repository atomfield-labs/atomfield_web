"""
Access control: every user sees and deletes only their own work, and
key creation is rate-limited per client address.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.dependencies import client_address
from app.core.config import settings
from app.storage.keys import upload_key

UserHeadersFactory = Callable[..., dict[str, str]]
XYZ_WATER = "3\nwater\nO 0 0 0\nH 0.76 0.59 0\nH -0.76 0.59 0\n"


def submit_job(client: TestClient, headers: dict[str, str]) -> str:
    """
    Submit one standalone job and return its id.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Owner's key headers.
    :type headers: dict[str, str]
    :return: New job id.
    :rtype: str
    """
    response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": {}},
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()["id"]


def job_paths(job_id: str) -> list[str]:
    """
    List every read route that exposes one job.

    :param job_id: Job id.
    :type job_id: str
    :return: URL paths.
    :rtype: list[str]
    """
    base = f"/api/jobs/{job_id}"
    return [base, f"{base}/logs", f"{base}/files"]


def count_jobs(client: TestClient, headers: dict[str, str]) -> int:
    """
    Count the caller's jobs.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Caller's key headers.
    :type headers: dict[str, str]
    :return: Total jobs visible to the caller.
    :rtype: int
    """
    return client.get("/api/jobs", headers=headers).json()["total"]


def test_job_routes_require_a_key(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Reading a job without a key is rejected, even with a valid job id.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    job_id = submit_job(client, make_user_headers())
    for path in job_paths(job_id):
        assert client.get(path).status_code == 401, path


def test_other_users_jobs_are_not_found(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A stranger gets 404 on every route of someone else's job.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner = make_user_headers("owner")
    stranger = make_user_headers("stranger")
    job_id = submit_job(client, owner)
    for path in job_paths(job_id):
        assert client.get(path, headers=stranger).status_code == 404, path
        assert client.get(path, headers=owner).status_code == 200, path


def test_admin_can_read_any_job(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers: UserHeadersFactory,
):
    """
    The administrator may read every user's jobs.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Headers carrying the administrator key.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    job_id = submit_job(client, make_user_headers())
    response = client.get(f"/api/jobs/{job_id}", headers=admin_headers)
    assert response.status_code == 200


def test_clear_deletes_only_the_callers_jobs(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    "Clear" removes the caller's jobs and leaves everyone else's.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    clearing_user = make_user_headers("clearing_user")
    other_user = make_user_headers("other_user")
    submit_job(client, clearing_user)
    submit_job(client, other_user)

    assert client.delete("/api/jobs/clear").status_code == 401
    response = client.delete("/api/jobs/clear", headers=clearing_user)

    assert response.status_code == 200
    assert count_jobs(client, clearing_user) == 0
    assert count_jobs(client, other_user) == 1


def test_delete_session_cannot_touch_other_users(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers: UserHeadersFactory,
):
    """
    Deleting a session by name deletes only the caller's session: the
    stranger's delete leaves the owner's job and uploaded file; the
    owner's delete removes both.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Headers carrying the administrator key.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner_label = f"session_owner_{uuid.uuid4().hex[:6]}"
    owner = make_user_headers(owner_label)
    stranger = make_user_headers("session_stranger")
    payload = {
        "session_id": "same_session_name",
        "nodes": [{"ui_id": "a", "script_name": "toy_opt", "parameters": {}}],
        "edges": [],
        "files": [{"filename": "water.xyz", "content": XYZ_WATER}],
    }
    client.post("/api/jobs/pipeline/submit", json=payload, headers=owner)
    users = client.get("/api/admin/users", headers=admin_headers).json()
    owner_id = next(
        user["id"] for user in users["users"] if user["label"] == owner_label
    )
    store = client.app.state.store
    upload = upload_key(uuid.UUID(owner_id), "same_session_name", "water.xyz")

    path = "/api/jobs/session/same_session_name"
    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=stranger).status_code == 200
    assert count_jobs(client, owner) == 1
    assert store.existing_path(upload) is not None

    assert client.delete(path, headers=owner).status_code == 200
    assert count_jobs(client, owner) == 0
    assert store.existing_path(upload) is None


def test_nobody_gets_a_key_without_signing_in(client: TestClient):
    """
    There is no way to get an account, or a key, without signing in
    with an institute account: the old open route is gone.

    :param client: In-process API client.
    :type client: TestClient
    """
    anonymous = client.post("/api/auth/keys", json={"label": "stranger"})
    assert anonymous.status_code == 404


def test_forged_proxy_header_is_ignored_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Without TRUST_PROXY_HEADERS, a caller cannot pick its own address.

    :param monkeypatch: Ensures the default (untrusted) setting.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    request = Request(
        {
            "type": "http",
            "headers": [(b"cf-connecting-ip", b"198.51.100.9")],
            "client": ("10.0.0.5", 50000),
        }
    )
    assert client_address(request) == "10.0.0.5"
