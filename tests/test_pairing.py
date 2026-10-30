"""
Pairing an agent with a short code: the agent asks and waits, the
person approves the code in the web app, and only the agent that
asked collects the token, once.
"""

import asyncio
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.pairing import Pairings
from app.core.config import settings
from app.schemas.pairings import PairingRequest
from tests.browser import OWN_PAGE, STUDENT, sign_in
from tests.conftest import UserHeadersFactory
from tests.fake_google import FakeGoogle
from tests.stores import make_redis

AGENT_PAIRINGS = "/api/agent/pairings"
PAIRINGS = "/api/pairings"
MACHINE = {"hostname": "login1", "username": "ada", "kind": "slurm"}
CLUSTER = {"name": "Lab cluster"}


def start(client: TestClient) -> dict:
    """
    An agent asking to be paired.

    :param client: In-process API client, here the agent.
    :type client: TestClient
    :return: Its code and secret.
    :rtype: dict
    """
    started = client.post(AGENT_PAIRINGS, json=MACHINE)
    assert started.status_code == 201
    return started.json()


def collect(
    client: TestClient, started: dict, secret: str | None = None
) -> httpx.Response:
    """
    The agent asking whether its code was approved.

    :param client: In-process API client, here the agent.
    :type client: TestClient
    :param started: What the agent got when it asked.
    :type started: dict
    :param secret: A secret to send instead of the agent's own.
    :type secret: str | None
    :return: The answer.
    :rtype: httpx.Response
    """
    body = {"secret": secret or started["secret"]}
    return client.post(f"{AGENT_PAIRINGS}/{started['code']}/token", json=body)


def approve(client: TestClient, code: str) -> httpx.Response:
    """
    The signed-in person approving a code.

    :param client: In-process API client, here the browser.
    :type client: TestClient
    :param code: The code, as typed.
    :type code: str
    :return: The answer.
    :rtype: httpx.Response
    """
    return client.post(f"{PAIRINGS}/{code}", json=CLUSTER, headers=OWN_PAGE)


def token_works(client: TestClient, token: str) -> bool:
    """
    Whether the API accepts an agent token (a heartbeat with no jobs
    changes nothing).

    :param client: In-process API client, here the agent.
    :type client: TestClient
    :param token: The agent token.
    :type token: str
    :return: True if accepted.
    :rtype: bool
    """
    beat = client.post(
        "/api/agent/heartbeat",
        json={"jobs": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    return beat.status_code == 200


def test_an_agent_is_paired_by_its_signed_in_owner(
    client: TestClient, google: FakeGoogle
):
    """
    The agent waits; the person sees which machine asks, approves it;
    the agent collects a working token, once; the cluster is theirs.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    started = start(client)
    waiting = collect(client, started)
    seen = client.get(f"{PAIRINGS}/{started['code']}").json()
    approved = approve(client, started["code"])
    token = collect(client, started).json()["token"]
    names = [target["name"] for target in client.get("/api/targets").json()]
    assert waiting.status_code == 202
    assert (seen["hostname"], seen["username"]) == ("login1", "ada")
    assert approved.json()["name"] == CLUSTER["name"] in names
    assert token_works(client, token)
    assert collect(client, started).status_code == 404


def test_only_the_agent_that_asked_collects_the_token(
    client: TestClient, google: FakeGoogle
):
    """
    Knowing the code is not enough to take the token: the asking
    agent's secret is needed too.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    started = start(client)
    approve(client, started["code"])
    stolen = collect(client, started, secret="someone-elses-guess")
    assert stolen.status_code == 404
    assert collect(client, started).status_code == 200


def test_a_code_is_found_however_it_is_typed(
    client: TestClient, google: FakeGoogle
):
    """
    Lower case, spaces and a missing dash are forgiven.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    started = start(client)
    typed = f" {started['code'].replace('-', '').lower()} "
    assert client.get(f"{PAIRINGS}/{typed}").status_code == 200


def test_a_code_is_approved_once(client: TestClient, google: FakeGoogle):
    """
    A second approval of the same code finds nothing waiting, so no
    second cluster is made.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    started = start(client)
    first = approve(client, started["code"])
    second = approve(client, started["code"])
    assert (first.status_code, second.status_code) == (200, 404)


def test_a_key_cannot_approve_a_pairing(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    Approving makes a credential, so like keys it needs a signed-in
    browser: a leaked key cannot pair a stranger's machine.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    started = start(client)
    script = make_user_headers()
    refused = client.post(
        f"{PAIRINGS}/{started['code']}", json=CLUSTER, headers=script
    )
    assert refused.status_code == 403


def test_an_unknown_code_finds_nothing(client: TestClient, google: FakeGoogle):
    """
    A code nobody asked for (or one that expired) shows nothing.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    assert client.get(f"{PAIRINGS}/BCDF-GHJK").status_code == 404


def test_a_flood_of_pairings_from_one_address_is_turned_back(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Each pairing holds memory in Redis for minutes, so one address may
    ask only a few times a minute.

    :param client: In-process API client.
    :type client: TestClient
    :param monkeypatch: Lowers the limit and trusts the proxy header.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(settings, "PAIRING_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    address = {"CF-Connecting-IP": f"203.0.113.{uuid.uuid4().int % 250 + 1}"}
    statuses = [
        client.post(AGENT_PAIRINGS, json=MACHINE, headers=address).status_code
        for _ in range(3)
    ]
    assert statuses == [201, 201, 429]


async def approve_twice_at_once() -> list[bool]:
    """
    Two approvals of one code racing: each tries to claim it.

    :return: Whether each claim won.
    :rtype: list[bool]
    """
    redis = make_redis()
    try:
        pairings = Pairings(redis)
        pairing, _ = await pairings.start(PairingRequest(**MACHINE), "here")
        claims = (pairings.claim_approval(pairing.code) for _ in range(2))
        return list(await asyncio.gather(*claims))
    finally:
        await redis.aclose()


def test_two_approvals_at_once_make_one_cluster(client: TestClient):
    """
    A double click, or two people with one code, approving together:
    only the first claim wins, so only one cluster is made.

    :param client: In-process API client (its fixture readies Redis).
    :type client: TestClient
    """
    assert sorted(asyncio.run(approve_twice_at_once())) == [False, True]
