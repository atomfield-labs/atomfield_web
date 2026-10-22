"""
Submissions are checked against the task catalog before anything is
stored, and the catalog itself is served to the UI.
"""

from collections.abc import Callable

from fastapi.testclient import TestClient

UserHeadersFactory = Callable[..., dict[str, str]]


def error_locations(response) -> list[list]:
    """
    List the field locations of a 422 response.

    :param response: HTTP response.
    :type response: httpx.Response
    :return: Each error's location.
    :rtype: list[list]
    """
    return [item["loc"] for item in response.json()["detail"]]


def test_task_definitions_are_public(client: TestClient):
    """
    The menu loads without a key, in catalog order.

    :param client: In-process API client.
    :type client: TestClient
    """
    response = client.get("/api/task-definitions")
    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == [
        "toy_opt",
        "toy_network",
    ]


def test_unknown_task_is_rejected_at_its_field(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A task id missing from the catalog gets a 422 at ``script_name``.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    response = client.post(
        "/api/jobs/submit",
        json={"script_name": "rm_rf", "parameters": {}},
        headers=make_user_headers(),
    )
    assert response.status_code == 422
    assert error_locations(response) == [["body", "script_name"]]


def test_every_bad_node_is_reported_at_once(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Errors from several nodes come back together, each located at the
    exact parameter, and nothing is stored or charged to the quota.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    payload = {
        "nodes": [
            {
                "ui_id": "a",
                "script_name": "toy_opt",
                "parameters": {"optlevel": "vtight"},
            },
            {"ui_id": "b", "script_name": "toy_network", "parameters": {}},
        ],
        "edges": [],
    }

    response = client.post(
        "/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
    assert error_locations(response) == [
        ["body", "nodes", 0, "parameters", "optlevel"],
        ["body", "nodes", 1, "inputs", "reference"],
        ["body", "nodes", 1, "parameters", "method"],
    ]
    stats = client.get("/api/auth/stats", headers=headers).json()
    assert stats["total_jobs"] == 0
    assert stats["quota_used"] == 0


def test_stored_jobs_record_every_value(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A job stores its submitted values plus every default it ran with.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": {"charge": -1}},
        headers=make_user_headers(),
    )
    assert response.status_code == 202
    parameters = response.json()["parameters"]
    assert parameters["charge"] == -1
    assert parameters["temp"] == 300.0
    assert parameters["optlevel"] == "normal"
