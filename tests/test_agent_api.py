"""
The agent API: token auth, long-poll claims, heartbeats that renew
leases and carry cancel requests, and completions guarded by attempt
number and agent identity.
"""

import asyncio
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.security import hash_api_key
from app.models.compute_target import HOUSE_TARGET_ID, ComputeTarget
from app.models.job import Job
from app.models.run import Run
from app.queue.job_queue import RedisJobQueue
from tests.fake_pack import WATER_XYZ
from tests.graphs import run_counter
from tests.stores import make_redis

UserHeadersFactory = Callable[..., dict[str, str]]
HOUSE = {"Authorization": f"Bearer {settings.HOUSE_AGENT_TOKEN}"}
OTHER_TOKEN = "af_agent_test_other"
SHORT_WAIT = {"wait_seconds": 0.2}


def enqueue(*job_ids: str) -> None:
    """
    Put job ids on the house agent's queue, as the dispatcher would.

    :param job_ids: Jobs to queue.
    :type job_ids: str
    """

    async def scenario():
        redis = make_redis()
        try:
            await RedisJobQueue(redis).add(
                HOUSE_TARGET_ID, [uuid.UUID(job_id) for job_id in job_ids]
            )
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def queue_size() -> int:
    """
    Count the jobs waiting for the house agent.

    :return: Queue length.
    :rtype: int
    """

    async def scenario():
        redis = make_redis()
        try:
            return await RedisJobQueue(redis).size(HOUSE_TARGET_ID)
        finally:
            await redis.aclose()

    return asyncio.run(scenario())


def drain_queue() -> None:
    """
    Empty the house queue so each test starts clean.
    """

    async def scenario():
        redis = make_redis()
        try:
            await redis.delete(f"queue:{HOUSE_TARGET_ID}")
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def submit_chain(client: TestClient, headers: dict[str, str]) -> list[str]:
    """
    Submit a two-job chain (first -> second) and return their ids.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Owner's key headers.
    :type headers: dict[str, str]
    :return: [first job id, second job id].
    :rtype: list[str]
    """
    payload = {
        "nodes": [
            {"ui_id": "first", "script_name": "toy_opt"},
            {"ui_id": "second", "script_name": "toy_opt"},
        ],
        "edges": [{"upstream_ui_id": "first", "downstream_ui_id": "second"}],
    }
    response = client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=headers
    )
    assert response.status_code == 202
    ids = response.json()["job_ids"]
    return [ids["first"], ids["second"]]


@pytest.fixture
def chain(client: TestClient, make_user_headers: UserHeadersFactory):
    """
    A fresh two-job chain; submitting it put the first job (only) on
    the house queue.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :return: (owner headers, [first id, second id]).
    :rtype: tuple[dict[str, str], list[str]]
    """
    drain_queue()
    headers = make_user_headers()
    return headers, submit_chain(client, headers)


def claim(client: TestClient, headers: dict[str, str] = HOUSE):
    """
    Ask for a job with a short wait.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Agent headers.
    :type headers: dict[str, str]
    :return: HTTP response.
    :rtype: httpx.Response
    """
    return client.post("/api/agent/claims", json=SHORT_WAIT, headers=headers)


def complete(client: TestClient, job_id: str, attempt: int, **extra):
    """
    Report a successful attempt.

    :param client: In-process API client.
    :type client: TestClient
    :param job_id: Finished job.
    :type job_id: str
    :param attempt: Attempt being reported.
    :type attempt: int
    :param extra: Overrides, e.g. ``headers``.
    :type extra: Any
    :return: HTTP response.
    :rtype: httpx.Response
    """
    headers = extra.pop("headers", HOUSE)
    body = {"attempt": attempt, "outcome": "succeeded", **extra}
    return client.post(
        f"/api/agent/jobs/{job_id}/complete", json=body, headers=headers
    )


def test_agent_routes_need_an_agent_token(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    No token, an unknown token, or a user's API key: all 401.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    user_key = make_user_headers()["X-API-Key"]
    for headers in ({}, {"Authorization": "Bearer nope"},
                    {"Authorization": f"Bearer {user_key}"}):  # fmt: skip
        assert claim(client, headers).status_code == 401


def test_an_empty_queue_answers_204_after_waiting(client: TestClient):
    """
    With nothing to do, the server waits, then sends an empty answer.

    :param client: In-process API client.
    :type client: TestClient
    """
    drain_queue()
    assert claim(client).status_code == 204


def test_submitting_queues_only_jobs_with_no_parents(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Both ways in put work on the queue right after saving it: a single
    job at once, a pipeline only its first job (the second waits).

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    drain_queue()
    headers = make_user_headers()
    submit_chain(client, headers)
    assert queue_size() == 1
    single = {"script_name": "toy_opt", "parameters": {}}
    response = client.post("/api/jobs/submit", json=single, headers=headers)
    assert response.status_code == 202
    assert queue_size() == 2


def test_a_claim_starts_attempt_one(client: TestClient, chain):
    """
    The agent gets the task definition, values and inputs, and the job
    is now running under attempt 1.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    headers, (first, _) = chain
    assignment = claim(client).json()
    assert assignment["job_id"] == first
    assert assignment["attempt"] == 1
    assert assignment["task"]["id"] == "toy_opt"
    assert assignment["parameters"]["optlevel"] == "normal"
    job = client.get(f"/api/jobs/{first}", headers=headers).json()
    assert job["status"] == "running"


def test_a_duplicate_message_is_claimed_once(client: TestClient, chain):
    """
    Fault test 6: the same job delivered twice runs once; the second
    message is recognised as stale and skipped.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    _, (first, _) = chain
    assert claim(client).status_code == 200
    enqueue(first)  # e.g. the sweeper re-sent it
    assert claim(client).status_code == 204


def test_success_queues_the_children(client: TestClient, chain):
    """
    Completing the first job puts the second on the agent's queue.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    headers, (first, second) = chain
    claim(client)
    response = complete(client, first, 1, output_data={"energy": -5.07})
    assert response.json() == {
        "job_id": first,
        "status": "succeeded",
        "children_queued": 1,
        "pack": [],
    }
    assert queue_size() == 1
    child = client.get(f"/api/jobs/{second}", headers=headers).json()
    assert child["status"] == "queued"


def test_changes_made_through_the_api_are_numbered(
    client: TestClient,
    chain,
    make_session: async_sessionmaker,
):
    """
    Claiming and finishing the first job announces three changes (it
    started, it succeeded, the second became queued).

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    _, (first, _) = chain
    attempt = claim(client).json()["attempt"]
    assert complete(client, first, attempt).status_code == 200

    async def read_counter() -> int:
        async with make_session() as session:
            return await run_counter(session, uuid.UUID(first))

    assert asyncio.run(read_counter()) == 3


def test_stale_and_repeated_reports_get_409(client: TestClient, chain):
    """
    Fault test 7: a report for the wrong attempt is refused and changes
    nothing; so is a second report for the right one.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    _, (first, _) = chain
    claim(client)
    assert complete(client, first, 2).status_code == 409
    assert complete(client, first, 1).status_code == 200
    assert complete(client, first, 1).status_code == 409


def test_another_agent_cannot_finish_the_job(
    client: TestClient,
    chain,
    make_session: async_sessionmaker,
):
    """
    Guessing the attempt number is not enough: only the agent holding
    the job may finish it.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def add_other_agent():
        async with make_session() as session:
            session.add(
                ComputeTarget(
                    name="other", token_hash=hash_api_key(OTHER_TOKEN)
                )
            )
            await session.commit()

    asyncio.run(add_other_agent())
    _, (first, _) = chain
    claim(client)
    other = {"Authorization": f"Bearer {OTHER_TOKEN}"}
    assert complete(client, first, 1, headers=other).status_code == 409


def test_heartbeats_carry_cancel_and_abandon(
    client: TestClient,
    chain,
    make_session: async_sessionmaker,
):
    """
    A held attempt is renewed; a cancel request comes back as "cancel";
    an attempt the agent no longer holds comes back as "abandon".

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    _, (first, _) = chain
    claim(client)

    def beat(attempt: int) -> dict:
        body = {"jobs": [{"job_id": first, "attempt": attempt}]}
        return client.post(
            "/api/agent/heartbeat", json=body, headers=HOUSE
        ).json()

    assert beat(1) == {"cancel": [], "abandon": [], "pack": []}

    async def request_cancel():
        async with make_session() as session:
            await session.execute(
                update(Job)
                .where(Job.id == uuid.UUID(first))
                .values(cancel_requested=True)
            )
            await session.commit()

    asyncio.run(request_cancel())
    assert beat(1)["cancel"] == [{"job_id": first, "attempt": 1}]
    assert beat(7)["abandon"] == [{"job_id": first, "attempt": 7}]


def test_a_run_cannot_take_another_users_upload(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    Uploads are kept under their owner's folder, chosen from the
    caller's key, never from the request. A stranger submitting under
    the same session name and asking for the owner's file gets a link
    into their own (empty) folder; the owner's run gets the file.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    owner, stranger = make_user_headers(), make_user_headers()
    name = f"owned_{uuid.uuid4().hex[:6]}.xyz"
    uploaded = client.post(
        "/api/files/upload",
        files={"file": (name, WATER_XYZ, "text/plain")},
        data={"session_id": "shared_name"},
        headers=owner,
    )
    assert uploaded.status_code == 201

    def fetch_input(headers: dict[str, str]):
        drain_queue()
        node = {
            "ui_id": "opt",
            "script_name": "toy_opt",
            "inputs": {"structure": [name]},
        }
        payload = {"session_id": "shared_name", "nodes": [node], "edges": []}
        submitted = client.post(
            "/api/jobs/pipeline/submit", json=payload, headers=headers
        )
        assert submitted.status_code == 202
        link = claim(client).json()["inputs"][0]["url"]
        return client.get(link)

    assert fetch_input(stranger).status_code == 404
    mine = fetch_input(owner)
    assert mine.status_code == 200
    assert mine.text == WATER_XYZ


def test_a_claim_names_the_folder_and_the_parents(
    client: TestClient,
    chain,
):
    """
    The second job's assignment carries its folder name and its
    parent's, so the agent can link ``upstream/first``.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    _, (first, second) = chain
    first_assignment = claim(client).json()
    assert (first_assignment["node_key"], first_assignment["parents"]) == (
        "first",
        [],
    )
    complete(client, first, first_assignment["attempt"])
    second_assignment = claim(client).json()
    assert second_assignment["job_id"] == second
    assert second_assignment["node_key"] == "second"
    assert second_assignment["parents"] == ["first"]


def test_every_job_of_a_run_receives_the_sessions_uploads(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A file attached to the submission reaches every job's folder, as
    the session folder did before: scripts with an optional input
    look for it there.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    drain_queue()
    headers = make_user_headers()
    payload = {
        "nodes": [
            {"ui_id": "first", "script_name": "toy_opt"},
            {"ui_id": "second", "script_name": "toy_opt"},
        ],
        "edges": [{"upstream_ui_id": "first", "downstream_ui_id": "second"}],
        "files": [{"filename": "water.xyz", "content": WATER_XYZ}],
    }
    ids = client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=headers
    ).json()["job_ids"]

    first = claim(client).json()
    complete(client, ids["first"], first["attempt"])
    second = claim(client).json()

    for assignment in (first, second):
        (only,) = assignment["inputs"]
        assert only["name"] == "water.xyz"
        assert client.get(only["url"]).text == WATER_XYZ


def test_a_finished_jobs_log_and_files_come_from_its_report(
    client: TestClient,
    chain,
    make_session: async_sessionmaker,
):
    """
    The agent uploads the log through a link it asked for, then reports
    every file and where the run's folder is. The UI's log and file
    list come from there; a stale attempt or a path gets no link.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    headers, (first, _) = chain
    attempt = claim(client).json()["attempt"]
    uploads_url = f"/api/agent/jobs/{first}/uploads"

    def ask(names: list[str]):
        body = {"attempt": attempt, "names": names}
        return client.post(uploads_url, json=body, headers=HOUSE)

    assert ask(["../escape.log"]).status_code == 422
    link = ask(["toy_opt.log"]).json()["links"]["toy_opt.log"]
    assert client.put(link, content=b"converged in 7 steps").status_code == 201
    cards = [
        {
            "path": "toy_opt.log",
            "size_bytes": 20,
            "sha256": "a" * 64,
            "uploaded": True,
        },
        {"path": "md/frames.trj", "size_bytes": 10**9, "sha256": "b" * 64},
    ]
    folder = {"path": "/scratch/you/runs/r", "address": "you@login.hpc.edu"}
    finished = complete(client, first, attempt, files=cards, folder=folder)
    assert finished.status_code == 200

    logs = client.get(f"/api/jobs/{first}/logs", headers=headers).json()
    assert logs["logs"] == "converged in 7 steps"
    assert logs["artifacts"] == ["toy_opt.log", "md/frames.trj"]
    assert ask(["late.log"]).status_code == 409

    async def read_folder():
        async with make_session() as session:
            job = await session.get(Job, uuid.UUID(first))
            run = await session.get(Run, job.run_id)
            return run.folder_path, run.folder_address

    assert asyncio.run(read_folder()) == (folder["path"], folder["address"])
