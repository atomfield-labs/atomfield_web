import time
import uuid

import requests

BASE_URL = "http://localhost:8000"


def get_auth_headers(label: str = "pytest_test_key") -> dict[str, str]:
    res = requests.post(
        f"{BASE_URL}/api/auth/keys",
        json={"label": label},
    )
    assert res.status_code == 201
    key = res.json()["api_key"]
    return {"X-API-Key": key}


def test_health_check():
    res = requests.get(f"{BASE_URL}/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data


def test_unauthenticated_requests_blocked():
    res_job = requests.post(
        f"{BASE_URL}/api/jobs/submit",
        json={"script_name": "test.py", "parameters": {}},
    )
    assert res_job.status_code == 401

    res_pipeline = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json={
            "nodes": [
                {"ui_id": "a", "script_name": "test.py", "parameters": {}}
            ],
            "edges": [],
        },
    )
    assert res_pipeline.status_code == 401


def test_auth_key_lifecycle_and_user_stats():
    auth_headers = get_auth_headers("stats_test_key")

    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["label"] == "stats_test_key"
    assert me_data["quota_used"] == 0

    res_stats_init = requests.get(
        f"{BASE_URL}/api/auth/stats", headers=auth_headers
    )
    assert res_stats_init.status_code == 200
    stats_init = res_stats_init.json()
    assert stats_init["total_jobs"] == 0
    assert stats_init["quota_remaining"] == stats_init["quota_limit"]

    res_submit = requests.post(
        f"{BASE_URL}/api/jobs/submit",
        json={"script_name": "sample_script.py", "parameters": {}},
        headers=auth_headers,
    )
    assert res_submit.status_code == 202

    res_stats_after = requests.get(
        f"{BASE_URL}/api/auth/stats", headers=auth_headers
    )
    assert res_stats_after.status_code == 200
    stats_after = res_stats_after.json()
    assert stats_after["total_jobs"] == 1
    assert stats_after["quota_used"] == 1


def test_path_traversal_prevention_file_upload():
    # Attempt directory traversal via malicious session_id
    files = {"file": ("test.xyz", "1\nwater\nO 0.0 0.0 0.0\n", "text/plain")}
    data = {"session_id": "../../etc/evil"}
    res = requests.post(f"{BASE_URL}/api/files/upload", files=files, data=data)
    assert res.status_code in (200, 201)
    meta = res.json()
    assert ".." not in meta["workspace_path"]
    assert meta["formula"] == "O"


def test_path_traversal_prevention_zip_download():
    # Attempt traversal in artifacts download endpoint
    res = requests.get(
        f"{BASE_URL}/api/jobs/artifacts/download?session_id=../../../../etc"
    )
    assert res.status_code == 200
    assert res.headers.get("content-type") == "application/zip"


def test_dag_cycle_detection():
    # Node A -> Node B -> Node A (Cycle)
    payload = {
        "nodes": [
            {"ui_id": "node_A", "script_name": "simulate.py", "parameters": {}},
            {"ui_id": "node_B", "script_name": "simulate.py", "parameters": {}},
        ],
        "edges": [
            {"upstream_ui_id": "node_A", "downstream_ui_id": "node_B"},
            {"upstream_ui_id": "node_B", "downstream_ui_id": "node_A"},
        ],
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 400
    assert "contains a cycle" in res.json()["detail"]


def test_dag_invalid_edge_endpoints():
    payload = {
        "nodes": [
            {"ui_id": "node_A", "script_name": "simulate.py", "parameters": {}},
        ],
        "edges": [
            {
                "upstream_ui_id": "node_A",
                "downstream_ui_id": "non_existent_node",
            },
        ],
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 400
    assert "references invalid node ID" in res.json()["detail"]


def test_standalone_job_submission_with_null_parameters():
    payload = {
        "script_name": "simulate.py",
        "parameters": None,
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code in (200, 201, 202)
    job_data = res.json()
    assert job_data["status"] == "Pending"
    assert "user_id" in job_data["parameters"]


def test_valid_dag_submission_and_status():
    session_id = f"test_valid_dag_{uuid.uuid4().hex[:6]}"
    payload = {
        "session_id": session_id,
        "nodes": [
            {
                "ui_id": "node_1",
                "script_name": "simulate.py",
                "parameters": {"iterations": 5},
            },
            {
                "ui_id": "node_2",
                "script_name": "simulate.py",
                "parameters": {"iterations": 10},
            },
        ],
        "edges": [{"upstream_ui_id": "node_1", "downstream_ui_id": "node_2"}],
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code in (200, 201, 202)
    data = res.json()
    assert data["status"] == "success"
    assert data["total_nodes"] == 2
    assert data["roots_started"] == 1
    assert "node_1" in data["job_ids"]
    assert "node_2" in data["job_ids"]

    node1_id = data["job_ids"]["node_1"]
    node2_id = data["job_ids"]["node_2"]

    # Check node 1 status
    res_node1 = requests.get(f"{BASE_URL}/api/jobs/{node1_id}")
    assert res_node1.status_code == 200
    assert res_node1.json()["status"] in (
        "Pending",
        "Running",
        "Success",
        "Failed",
    )

    # Check node 2 status
    res_node2 = requests.get(f"{BASE_URL}/api/jobs/{node2_id}")
    assert res_node2.status_code == 200
    assert res_node2.json()["status"] in (
        "Blocked",
        "Pending",
        "Running",
        "Success",
        "Failed",
    )


def test_job_logs_tailing():
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/submit",
        json={"script_name": "sample_script.py", "parameters": {}},
        headers=headers,
    )
    assert res.status_code in (200, 201, 202)
    job_id = res.json()["id"]

    res_logs = requests.get(f"{BASE_URL}/api/jobs/{job_id}/logs")
    assert res_logs.status_code == 200
    log_data = res_logs.json()
    assert "logs" in log_data
    assert "artifacts" in log_data
    assert isinstance(log_data["artifacts"], list)


def test_cascading_failure_propagation():
    session_id = f"test_cascade_{uuid.uuid4().hex[:6]}"
    payload = {
        "session_id": session_id,
        "nodes": [
            {
                "ui_id": "root_failing",
                "script_name": "nonexistent_script.py",
                "parameters": {},
            },
            {
                "ui_id": "downstream_child",
                "script_name": "simulate.py",
                "parameters": {},
            },
            {
                "ui_id": "downstream_grandchild",
                "script_name": "simulate.py",
                "parameters": {},
            },
        ],
        "edges": [
            {
                "upstream_ui_id": "root_failing",
                "downstream_ui_id": "downstream_child",
            },
            {
                "upstream_ui_id": "downstream_child",
                "downstream_ui_id": "downstream_grandchild",
            },
        ],
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code in (200, 201, 202)
    job_ids = res.json()["job_ids"]

    # Allow worker to pick up and fail the root node
    cascaded = False
    for _ in range(15):
        time.sleep(1)
        r_child = requests.get(
            f"{BASE_URL}/api/jobs/{job_ids['downstream_child']}"
        ).json()
        r_grandchild = requests.get(
            f"{BASE_URL}/api/jobs/{job_ids['downstream_grandchild']}"
        ).json()
        if r_child["status"] == "Failed" and r_grandchild["status"] == "Failed":
            assert r_child["error_message"] == "Upstream dependency failed"
            assert r_grandchild["error_message"] == "Upstream dependency failed"
            cascaded = True
            break

    assert cascaded, (
        "Child and grandchild did not transition to Failed on upstream failure"
    )


def test_successful_dag_execution_and_injection():
    session_id = f"test_success_dag_{uuid.uuid4().hex[:6]}"
    payload = {
        "session_id": session_id,
        "nodes": [
            {
                "ui_id": "upstream_node",
                "script_name": "sample_script.py",
                "parameters": {},
            },
            {
                "ui_id": "downstream_node",
                "script_name": "sample_script.py",
                "parameters": {},
            },
        ],
        "edges": [
            {
                "upstream_ui_id": "upstream_node",
                "downstream_ui_id": "downstream_node",
            },
        ],
    }
    headers = get_auth_headers()
    res = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert res.status_code in (200, 201, 202)
    job_ids = res.json()["job_ids"]

    completed = False
    for _ in range(20):
        time.sleep(1)
        r_downstream = requests.get(
            f"{BASE_URL}/api/jobs/{job_ids['downstream_node']}"
        ).json()
        if r_downstream["status"] == "Success":
            completed = True
            params = r_downstream.get("parameters", {})
            assert "upstream_results" in params
            assert job_ids["upstream_node"] in params["upstream_results"]
            break

    assert completed, "Downstream node did not succeed after upstream completed"
