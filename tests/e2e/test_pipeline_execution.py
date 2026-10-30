"""
End-to-end pipeline tests against a running stack (API, worker, Redis,
Postgres). Skipped by default; run with ``pytest -m e2e`` after
``docker compose up``, with ``ADMIN_API_KEY`` exported as the server's
own: people sign in with Google, so the tests act as the administrator.
"""

import os
import time
import uuid
from itertools import pairwise

import pytest
import requests

pytestmark = pytest.mark.e2e

# Point at another stack with ATOMFIELD_E2E_URL=http://host:port.
BASE_URL = os.environ.get("ATOMFIELD_E2E_URL", "http://localhost:8000")
POLL_ATTEMPTS = 20
POLL_INTERVAL_SECONDS = 1.0
UPSTREAM_FAILED_MESSAGE = "Upstream dependency failed"
WATER_XYZ = "3\nwater\nO 0 0 0.117\nH 0 0.757 -0.467\nH 0 -0.757 -0.467\n"


def runner_headers() -> dict[str, str]:
    """
    Headers for the person the tests run as: the administrator, whose
    key the running server made from its ``ADMIN_API_KEY``.

    :return: Headers carrying the administrator's key.
    :rtype: dict[str, str]
    """
    return {"X-API-Key": os.environ["ADMIN_API_KEY"]}


def build_chain(nodes: list[dict], with_water: bool = False) -> dict:
    """
    Build a submit payload linking the given nodes in order.

    :param nodes: Node bodies (ui_id, script_name, parameters, inputs).
    :type nodes: list[dict]
    :param with_water: Attach ``water.xyz`` to the session.
    :type with_water: bool
    :return: JSON body for ``/api/jobs/pipeline/submit``.
    :rtype: dict
    """
    edges = [
        {"upstream_ui_id": parent["ui_id"], "downstream_ui_id": child["ui_id"]}
        for parent, child in pairwise(nodes)
    ]
    files = [{"filename": "water.xyz", "content": WATER_XYZ}]
    return {
        "session_id": f"test_e2e_{uuid.uuid4().hex[:6]}",
        "nodes": nodes,
        "edges": edges,
        "files": files if with_water else [],
    }


def task_node(ui_id: str, task_id: str, **parameters) -> dict:
    """
    Describe one pipeline node running a catalog task.

    :param ui_id: Node id within the pipeline.
    :type ui_id: str
    :param task_id: Catalog task id.
    :type task_id: str
    :param parameters: Parameter values for the task.
    :type parameters: Any
    :return: Node body.
    :rtype: dict
    """
    return {"ui_id": ui_id, "script_name": task_id, "parameters": parameters}


def submit_pipeline(payload: dict, headers: dict[str, str]) -> dict[str, str]:
    """
    Submit a pipeline and return its node-to-job id mapping.

    :param payload: Pipeline submit body.
    :type payload: dict
    :param headers: Owner's key headers.
    :type headers: dict[str, str]
    :return: Mapping of node ui_id to job id.
    :rtype: dict[str, str]
    """
    response = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=payload,
        headers=headers,
    )
    assert response.status_code in (200, 201, 202)
    return response.json()["job_ids"]


def fetch_job(job_id: str, headers: dict[str, str]) -> dict:
    """
    Fetch one of the caller's jobs from the running server.

    :param job_id: Job identifier.
    :type job_id: str
    :param headers: Owner's key headers.
    :type headers: dict[str, str]
    :return: Job as returned by ``GET /api/jobs/{job_id}``.
    :rtype: dict
    """
    url = f"{BASE_URL}/api/jobs/{job_id}"
    return requests.get(url, headers=headers).json()


def test_cascading_failure_propagation():
    """
    A failing root marks its child and grandchild as upstream-failed.
    The root fails because it has no structure to optimize.
    """
    headers = runner_headers()
    nodes = [
        task_node("root_failing", "xtb_opt"),
        task_node("downstream_child", "xtb_md", time=0.2),
        task_node("downstream_grandchild", "rxn_network"),
    ]
    job_ids = submit_pipeline(build_chain(nodes), headers)
    descendants = [job_ids["downstream_child"]]
    descendants.append(job_ids["downstream_grandchild"])
    for _ in range(POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        jobs = [fetch_job(job_id, headers) for job_id in descendants]
        if all(job["status"] == "upstream_failed" for job in jobs):
            messages = {job["error_message"] for job in jobs}
            assert messages == {UPSTREAM_FAILED_MESSAGE}
            return
    pytest.fail("Descendants did not fail after the root failed")


def test_successful_dag_execution_and_injection():
    """
    A child runs after its parent succeeds and sees the parent's result.
    """
    headers = runner_headers()
    parent = task_node("upstream_node", "xtb_opt")
    parent["inputs"] = {"structure": ["water.xyz"]}
    nodes = [parent, task_node("downstream_node", "xtb_md", time=0.2)]
    job_ids = submit_pipeline(build_chain(nodes, with_water=True), headers)
    for _ in range(POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        child = fetch_job(job_ids["downstream_node"], headers)
        if child["status"] == "succeeded":
            upstream_results = child["parameters"]["upstream_results"]
            assert job_ids["upstream_node"] in upstream_results
            return
    pytest.fail("Downstream node did not succeed after its parent")
