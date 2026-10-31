"""
A person's pipelines on the server: saved and reopened, kept apart from
everyone else's, and showing how their newest run stands.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.api.routes import sessions as session_routes
from app.runs.states import JobStatus
from app.schemas.sessions import SessionState
from app.services.sessions import run_state

UserHeadersFactory = Callable[..., dict[str, str]]
SESSIONS = "/api/sessions"
SUBMIT_PIPELINE = "/api/jobs/pipeline/submit"
BLUEPRINT = {"nodes": [{"ui_id": "a", "label": "Step"}], "edges": []}
ONE_NODE = {
    "nodes": [{"ui_id": "a", "script_name": "toy_opt"}],
    "edges": [],
}


def new_id() -> str:
    """
    A session id nobody has used yet.

    :return: The id.
    :rtype: str
    """
    return f"pipeline_{uuid.uuid4().hex[:12]}"


def listed_ids(client: TestClient, headers: dict[str, str]) -> list[str]:
    """
    The ids on someone's sessions page.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Their key.
    :type headers: dict[str, str]
    :return: Ids, last changed first.
    :rtype: list[str]
    """
    return [item["id"] for item in client.get(SESSIONS, headers=headers).json()]


def test_a_draft_is_saved_and_reopens_whole(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    A saved draft comes back as it went in, from anywhere. The list
    leaves the draft itself out.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    session = new_id()
    body = {"title": "My run", "blueprint": BLUEPRINT, "node_count": 1}
    saved = client.put(f"{SESSIONS}/{session}", json=body, headers=headers)
    assert saved.status_code == 204

    opened = client.get(f"{SESSIONS}/{session}", headers=headers).json()
    assert opened["title"] == "My run"
    assert opened["blueprint"] == BLUEPRINT
    assert opened["node_count"] == 1
    assert opened["state"] == SessionState.DRAFT
    assert opened["run_id"] is None
    (listed,) = client.get(SESSIONS, headers=headers).json()
    assert (listed["id"], listed["title"]) == (session, "My run")
    assert "blueprint" not in listed


def test_saving_changes_only_what_is_sent(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    A new name leaves the draft alone, and an empty name makes the
    pipeline untitled again.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    path = f"{SESSIONS}/{new_id()}"
    client.put(path, json={"blueprint": BLUEPRINT}, headers=headers)
    client.put(path, json={"title": "Named"}, headers=headers)
    opened = client.get(path, headers=headers).json()
    assert (opened["title"], opened["blueprint"]) == ("Named", BLUEPRINT)
    client.put(path, json={"title": "  "}, headers=headers)
    opened = client.get(path, headers=headers).json()
    assert (opened["title"], opened["blueprint"]) == (None, BLUEPRINT)


def test_nobody_sees_anyone_elses_sessions(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    Someone else's session answers like one that does not exist, and is
    not on their list. Two people can even use the same id, each keeping
    their own, and deleting one leaves the other.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    mine, theirs = make_user_headers("me"), make_user_headers("them")
    session = new_id()
    path = f"{SESSIONS}/{session}"
    client.put(path, json={"title": "Mine"}, headers=mine)

    assert client.get(path, headers=theirs).status_code == 404
    assert listed_ids(client, theirs) == []

    client.put(path, json={"title": "Theirs"}, headers=theirs)
    assert client.get(path, headers=mine).json()["title"] == "Mine"
    assert client.get(path, headers=theirs).json()["title"] == "Theirs"

    gone = client.delete(f"/api/jobs/session/{session}", headers=theirs)
    assert gone.status_code == 200
    assert client.get(path, headers=theirs).status_code == 404
    assert client.get(path, headers=mine).json()["title"] == "Mine"


def test_sessions_need_someone_to_belong_to(client: TestClient):
    """
    Without a key or a sign-in there is nothing to see or save.

    :param client: In-process API client.
    :type client: TestClient
    """
    path = f"{SESSIONS}/{new_id()}"
    assert client.get(SESSIONS).status_code == 401
    assert client.get(path).status_code == 401
    assert client.put(path, json={"title": "x"}).status_code == 401


def test_a_run_is_noted_on_its_session(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    Submitting keeps the session's name and draft, and notes the run and
    which job each node became, so any computer can follow it. The next
    run takes its place.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    session = new_id()
    path = f"{SESSIONS}/{session}"
    body = {"title": "Named", "blueprint": BLUEPRINT}
    client.put(path, json=body, headers=headers)
    pipeline = {**ONE_NODE, "session_id": session}

    first = client.post(SUBMIT_PIPELINE, json=pipeline, headers=headers).json()
    opened = client.get(path, headers=headers).json()
    assert (opened["title"], opened["blueprint"]) == ("Named", BLUEPRINT)
    assert opened["run_id"] == first["run_id"]
    assert opened["job_ids"] == first["job_ids"]
    assert opened["node_count"] == 1
    assert opened["state"] == SessionState.WAITING

    second = client.post(SUBMIT_PIPELINE, json=pipeline, headers=headers).json()
    assert second["run_id"] != first["run_id"]
    assert (
        client.get(path, headers=headers).json()["run_id"] == second["run_id"]
    )


def test_a_script_run_is_listed_without_a_draft(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    A pipeline a script submits shows on the sessions page, untitled. A
    single job is not a pipeline, and does not.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    made = client.post(SUBMIT_PIPELINE, json=ONE_NODE, headers=headers).json()
    single = {"script_name": "toy_opt", "parameters": {}}
    client.post("/api/jobs/submit", json=single, headers=headers)
    (listed,) = client.get(SESSIONS, headers=headers).json()
    assert listed["id"] == made["pipeline_id"]
    assert listed["title"] is None
    opened = client.get(f"{SESSIONS}/{listed['id']}", headers=headers).json()
    assert opened["blueprint"] is None


def test_clearing_everything_clears_only_ones_own(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    Deleting all your sessions removes drafts as well as runs, and
    nobody else's.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    mine, theirs = make_user_headers("me"), make_user_headers("them")
    client.put(f"{SESSIONS}/{new_id()}", json={"title": "Draft"}, headers=mine)
    client.post(SUBMIT_PIPELINE, json=ONE_NODE, headers=mine)
    their_session = new_id()
    client.put(f"{SESSIONS}/{their_session}", json={}, headers=theirs)

    assert client.delete("/api/jobs/clear", headers=mine).status_code == 200
    assert listed_ids(client, mine) == []
    assert listed_ids(client, theirs) == [their_session]


def test_a_draft_over_the_limit_is_refused(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A draft too big to keep is refused, saying so, and nothing is made.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param monkeypatch: Lowers the limit.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(session_routes, "MAX_SESSION_BYTES", 10)
    headers = make_user_headers()
    path = f"{SESSIONS}/{new_id()}"
    refused = client.put(path, json={"blueprint": BLUEPRINT}, headers=headers)
    assert refused.status_code == 413
    assert client.get(path, headers=headers).status_code == 404


@pytest.mark.parametrize(
    ("jobs", "state"),
    [
        ([], SessionState.DRAFT),
        ([(JobStatus.QUEUED, False)], SessionState.WAITING),
        ([(JobStatus.RUNNING, False)], SessionState.WAITING),
        ([(JobStatus.RUNNING, True)], SessionState.RUNNING),
        (
            [(JobStatus.SUCCEEDED, True), (JobStatus.WAITING, False)],
            SessionState.WAITING,
        ),
        (
            [(JobStatus.FAILED, True), (JobStatus.RUNNING, True)],
            SessionState.RUNNING,
        ),
        (
            [(JobStatus.FAILED, True), (JobStatus.UPSTREAM_FAILED, False)],
            SessionState.FAILED,
        ),
        (
            [(JobStatus.SUCCEEDED, True), (JobStatus.CANCELLED, False)],
            SessionState.CANCELLED,
        ),
        ([(JobStatus.SUCCEEDED, True)], SessionState.DONE),
    ],
    ids=[
        "no-jobs",
        "queued",
        "in-a-clusters-queue",
        "running",
        "between-steps",
        "failed-but-still-working",
        "failed",
        "cancelled",
        "done",
    ],
)
def test_how_a_run_stands(jobs: list[tuple[str, bool]], state: SessionState):
    """
    Running only while a job really is; waiting while jobs remain with
    none working; afterwards, how it ended.

    :param jobs: Each job's status, and whether it has started.
    :type jobs: list[tuple[str, bool]]
    :param state: What it should read as.
    :type state: SessionState
    """
    assert run_state(jobs) == state
