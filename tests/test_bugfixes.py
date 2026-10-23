"""
Regression tests for API fixes: auth, path traversal, DAG validation,
submission, logs and session deletion. Runs the API in-process.
"""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

UserHeadersFactory = Callable[..., dict[str, str]]


def build_two_node_pipeline(session_id: str, script_name: str) -> dict:
    """
    Build a submit payload for a two-node chain, node_1 -> node_2.

    :param session_id: Session identifier for the pipeline.
    :type session_id: str
    :param script_name: Script both nodes run.
    :type script_name: str
    :return: JSON body for ``/api/jobs/pipeline/submit``.
    :rtype: dict
    """
    return {
        "session_id": session_id,
        "nodes": [
            {
                "ui_id": "node_1",
                "script_name": script_name,
                "parameters": {"charge": 0},
            },
            {
                "ui_id": "node_2",
                "script_name": script_name,
                "parameters": {"charge": 1},
            },
        ],
        "edges": [{"upstream_ui_id": "node_1", "downstream_ui_id": "node_2"}],
    }


def find_session_jobs(jobs: list[dict], session_id: str) -> list[dict]:
    """
    Select the jobs that belong to one pipeline session.

    :param jobs: Jobs as returned by ``GET /api/jobs``.
    :type jobs: list[dict]
    :param session_id: Session identifier to match.
    :type session_id: str
    :return: Jobs whose ``pipeline_id`` parameter matches.
    :rtype: list[dict]
    """
    return [
        job
        for job in jobs
        if job.get("parameters", {}).get("pipeline_id") == session_id
    ]


def test_health_check(client: TestClient):
    """
    The liveness probe answers with a status field.

    :param client: In-process API client.
    :type client: TestClient
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()


def test_unauthenticated_requests_blocked(client: TestClient):
    """
    Job and pipeline submission reject requests without a key.

    :param client: In-process API client.
    :type client: TestClient
    """
    job_response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": {}},
    )
    assert job_response.status_code == 401

    pipeline_response = client.post(
        "/api/jobs/pipeline/submit",
        json={
            "nodes": [
                {"ui_id": "a", "script_name": "toy_opt", "parameters": {}}
            ],
            "edges": [],
        },
    )
    assert pipeline_response.status_code == 401


def test_auth_key_lifecycle_and_user_stats(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A new key starts empty and its stats count each submission.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers("stats_test_key")

    me_data = client.get("/api/auth/me", headers=headers).json()
    assert me_data["label"] == "stats_test_key"
    assert me_data["quota_used"] == 0

    stats_before = client.get("/api/auth/stats", headers=headers).json()
    assert stats_before["total_jobs"] == 0
    assert stats_before["quota_remaining"] == stats_before["quota_limit"]

    submit_response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": {}},
        headers=headers,
    )
    assert submit_response.status_code == 202

    stats_after = client.get("/api/auth/stats", headers=headers).json()
    assert stats_after["total_jobs"] == 1
    assert stats_after["quota_used"] == 1


def test_path_traversal_prevention_file_upload(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A session id containing ``..`` cannot escape the workspace.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    files = {"file": ("test.xyz", "1\nwater\nO 0.0 0.0 0.0\n", "text/plain")}
    data = {"session_id": "../../etc/evil"}
    response = client.post(
        "/api/files/upload",
        files=files,
        data=data,
        headers=make_user_headers(),
    )
    assert response.status_code in (200, 201)
    meta = response.json()
    assert ".." not in meta["workspace_path"]
    assert meta["formula"] == "O"


def test_path_traversal_prevention_zip_download(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A traversal attempt in the download query returns a safe empty zip.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    response = client.get(
        "/api/jobs/artifacts/download",
        params={"session_id": "../../../../etc"},
        headers=make_user_headers(),
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/zip"


def test_dag_cycle_detection(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A pipeline with a cycle (A -> B -> A) is rejected with 400.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    payload = build_two_node_pipeline("cycle_session", "toy_opt")
    payload["edges"].append(
        {"upstream_ui_id": "node_2", "downstream_ui_id": "node_1"}
    )
    response = client.post(
        "/api/jobs/pipeline/submit",
        json=payload,
        headers=make_user_headers(),
    )
    assert response.status_code == 400
    assert "contains a cycle" in response.json()["detail"]


def test_dag_invalid_edge_endpoints(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    An edge pointing at an unknown node is rejected with 400.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    payload = {
        "nodes": [
            {"ui_id": "node_A", "script_name": "toy_opt", "parameters": {}},
        ],
        "edges": [
            {
                "upstream_ui_id": "node_A",
                "downstream_ui_id": "non_existent_node",
            },
        ],
    }
    response = client.post(
        "/api/jobs/pipeline/submit",
        json=payload,
        headers=make_user_headers(),
    )
    assert response.status_code == 400
    assert "references invalid node ID" in response.json()["detail"]


def test_standalone_job_submission_with_null_parameters(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A job submitted with ``parameters: null`` is accepted as Pending.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": None},
        headers=make_user_headers(),
    )
    assert response.status_code in (200, 201, 202)
    job_data = response.json()
    assert job_data["status"] == "queued"
    assert "user_id" in job_data["parameters"]


def test_valid_dag_submission_and_status(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A valid chain starts its root and blocks the child.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    session_id = f"test_valid_dag_{uuid.uuid4().hex[:6]}"
    headers = make_user_headers()
    response = client.post(
        "/api/jobs/pipeline/submit",
        json=build_two_node_pipeline(session_id, "toy_opt"),
        headers=headers,
    )
    assert response.status_code in (200, 201, 202)
    data = response.json()
    assert data["status"] == "success"
    assert data["total_nodes"] == 2
    assert data["roots_started"] == 1

    root_id = data["job_ids"]["node_1"]
    child_id = data["job_ids"]["node_2"]
    root = client.get(f"/api/jobs/{root_id}", headers=headers).json()
    child = client.get(f"/api/jobs/{child_id}", headers=headers).json()
    root_status, child_status = root["status"], child["status"]
    assert root_status == "queued"
    assert child_status == "waiting"


def test_job_logs_tailing(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    The logs endpoint returns log text and an artifact list.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    response = client.post(
        "/api/jobs/submit",
        json={"script_name": "toy_opt", "parameters": {}},
        headers=headers,
    )
    assert response.status_code in (200, 201, 202)
    job_id = response.json()["id"]

    log_response = client.get(f"/api/jobs/{job_id}/logs", headers=headers)
    assert log_response.status_code == 200
    log_data = log_response.json()
    assert "logs" in log_data
    assert isinstance(log_data["artifacts"], list)


def test_delete_session(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Deleting a session removes its jobs from the owner's job list.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers("delete_session_test_key")
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    payload = build_two_node_pipeline(session_id, "toy_opt")
    submit_response = client.post(
        "/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert submit_response.status_code in (200, 201, 202)

    jobs_before = client.get("/api/jobs", headers=headers).json()["jobs"]
    assert len(find_session_jobs(jobs_before, session_id)) == 2

    delete_response = client.delete(
        f"/api/jobs/session/{session_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "success"

    jobs_after = client.get("/api/jobs", headers=headers).json()["jobs"]
    assert find_session_jobs(jobs_after, session_id) == []
