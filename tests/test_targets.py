"""
Compute targets: a user adds a cluster, gets its agent token once,
and sends runs there; nobody else can see, use or change it.
"""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.models.compute_target import HOUSE_TARGET_ID
from tests.test_agent_api import HOUSE, claim, drain_queue

UserHeadersFactory = Callable[..., dict[str, str]]


def add_cluster(client: TestClient, headers: dict, name: str = "lab") -> dict:
    """
    Register a Slurm cluster for the caller.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Owner's key headers.
    :type headers: dict
    :param name: Target name.
    :type name: str
    :return: ``{"target": ..., "token": ...}``.
    :rtype: dict
    """
    response = client.post(
        "/api/targets", json={"name": name, "kind": "slurm"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()


def agent(token: str) -> dict[str, str]:
    """
    Headers of an agent holding ``token``.

    :param token: Agent token.
    :type token: str
    :return: Authorization header.
    :rtype: dict[str, str]
    """
    return {"Authorization": f"Bearer {token}"}


def submit_to(client: TestClient, headers: dict, target_id) -> dict:
    """
    Submit a one-job pipeline to a target.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Submitter's key headers.
    :type headers: dict
    :param target_id: Target id (or None for the shared server).
    :type target_id: str | None
    :return: HTTP response.
    :rtype: httpx.Response
    """
    payload = {
        "nodes": [{"ui_id": "only", "script_name": "toy_opt"}],
        "edges": [],
        "target_id": target_id,
    }
    return client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=headers
    )


def test_a_new_cluster_gets_a_token_shown_once(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    The token comes back on creation only; the list shows the shared
    server first and the cluster, offline until its agent calls in.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner = make_user_headers()
    created = add_cluster(client, owner)
    assert created["token"].startswith("af_agent_")

    listed = client.get("/api/targets", headers=owner).json()
    assert listed[0]["id"] == str(HOUSE_TARGET_ID)
    assert listed[0]["shared"] is True
    mine = listed[1]
    assert (mine["name"], mine["kind"], mine["online"]) == (
        "lab",
        "slurm",
        False,
    )
    assert "token" not in mine

    beat = {"jobs": []}
    token = agent(created["token"])
    beat_reply = client.post("/api/agent/heartbeat", json=beat, headers=token)
    assert beat_reply.status_code == 200
    assert client.get("/api/targets", headers=owner).json()[1]["online"]


def test_a_run_goes_only_to_its_targets_agent(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A run sent to the cluster waits in the cluster's queue: the house
    agent never sees it; the cluster's agent claims it.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    drain_queue()
    owner = make_user_headers()
    created = add_cluster(client, owner)
    submitted = submit_to(client, owner, created["target"]["id"])
    assert submitted.status_code == 202
    job_id = submitted.json()["job_ids"]["only"]

    assert claim(client, HOUSE).status_code == 204
    claimed = claim(client, agent(created["token"]))
    assert claimed.json()["job_id"] == job_id


def test_strangers_cannot_see_use_or_change_a_target(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    To anyone else the cluster does not exist: not listed, not usable
    for submissions, its token not replaceable, not removable.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner, stranger = make_user_headers(), make_user_headers()
    target_id = add_cluster(client, owner)["target"]["id"]

    listed = client.get("/api/targets", headers=stranger).json()
    assert target_id not in {target["id"] for target in listed}
    assert submit_to(client, stranger, target_id).status_code == 404
    rotate = f"/api/targets/{target_id}/token"
    assert client.post(rotate, headers=stranger).status_code == 404
    remove = f"/api/targets/{target_id}"
    assert client.delete(remove, headers=stranger).status_code == 404
    house = f"/api/targets/{HOUSE_TARGET_ID}"
    assert client.delete(house, headers=owner).status_code == 404
    unknown = str(uuid.uuid4())
    assert submit_to(client, owner, unknown).status_code == 404


def test_a_new_token_locks_out_the_old_one(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Replacing a lost or leaked token stops the old one at once.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner = make_user_headers()
    created = add_cluster(client, owner)
    rotate = f"/api/targets/{created['target']['id']}/token"
    fresh = client.post(rotate, headers=owner).json()["token"]

    beat = {"jobs": []}
    old = client.post(
        "/api/agent/heartbeat", json=beat, headers=agent(created["token"])
    )
    new = client.post("/api/agent/heartbeat", json=beat, headers=agent(fresh))
    assert (old.status_code, new.status_code) == (401, 200)


def test_a_retired_target_disappears_but_its_runs_remain(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Removing a cluster hides it and disables its token; its run is
    still there to look at.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner = make_user_headers()
    created = add_cluster(client, owner)
    target_id = created["target"]["id"]
    run_id = submit_to(client, owner, target_id).json()["run_id"]

    remove = f"/api/targets/{target_id}"
    assert client.delete(remove, headers=owner).status_code == 204
    listed = client.get("/api/targets", headers=owner).json()
    assert target_id not in {target["id"] for target in listed}
    beat = {"jobs": []}
    token = agent(created["token"])
    assert (
        client.post(
            "/api/agent/heartbeat", json=beat, headers=token
        ).status_code
        == 401
    )
    assert submit_to(client, owner, target_id).status_code == 404
    bundle = client.get(f"/api/runs/{run_id}/bundle", headers=owner)
    assert bundle.status_code == 200
