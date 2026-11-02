"""
One click of an AI button, from the route to the stored answer, with a
fake vendor: which steps can be reviewed, what is sent, and what the
person sees when anything goes wrong.
"""

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import ColumnElement, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.ai.reviews as reviews_module
from app.ai.evidence import EvidenceCollector
from app.ai.pages import PageLibrary
from app.ai.reviews import (
    INTERRUPTED,
    KEY_GONE,
    NOTHING_TO_READ,
    SECRET_CHANGED,
    SOMETHING_WRONG,
    TOO_SLOW,
    UNREADABLE,
    ReviewRunner,
)
from app.ai.suggestions import NOT_A_SETTING
from app.ai.vault import KeyVault
from app.ai.vendors import (
    KEY_REFUSED,
    OVER_LIMIT,
    AiVendor,
    LlmError,
    LlmReply,
)
from app.api.dependencies import get_key_vault, get_llm_factory
from app.api.routes.ai import NO_KEY_MESSAGE, NO_SECRET_MESSAGE
from app.catalog.catalog import Catalog
from app.catalog.models import ReferencePage
from app.core.config import settings
from app.main import app as atomfield
from app.models.ai import AiKey, AiReview, ReviewStatus
from app.models.compute_target import HOUSE_TARGET_ID
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.models.user import User
from app.runs.states import JobStatus
from app.services.job_service import delete_runs
from app.storage.keys import ai_sent_key, job_file_key
from tests.browser import OWN_PAGE, STUDENT, sign_in
from tests.conftest import UserHeadersFactory
from tests.fake_google import FakeGoogle
from tests.fake_vendors import FakeLlm

KEY_ROUTE = "/api/ai/key"
SECRET_KEY = "sk-test-key-that-must-never-show-1234"
NOBODY = "nobody@nowhere.invalid"
LOG = "starting\n" + "x" * 40 + "\nthe real error is here\n"
ANSWER = {
    "summary": "It did not converge.",
    "explanation": "**qe.log** shows it.",
    "suggestions": [
        {"setting": "temp", "value": "350", "why": "Warmer helps."},
        {"setting": "smearing_x", "value": "1", "why": "Made up."},
    ],
    "check_next": ["Run it again."],
}


def reply_of(text: str = json.dumps(ANSWER)) -> LlmReply:
    """
    What the fake vendor answers.

    :param text: The reply's text.
    :type text: str
    :return: The reply.
    :rtype: LlmReply
    """
    return LlmReply(
        text=text,
        model="model-that-answered",
        input_tokens=5,
        output_tokens=6,
    )


@pytest.fixture
def vendor(client: TestClient) -> Iterator[FakeLlm]:
    """
    A fake vendor in place of the real ones.

    :param client: In-process API client.
    :type client: TestClient
    :return: The fake.
    :rtype: Iterator[FakeLlm]
    """
    fake = FakeLlm(models=["some-model"], reply=reply_of())
    atomfield.dependency_overrides[get_llm_factory] = fake.factory
    yield fake
    del atomfield.dependency_overrides[get_llm_factory]


@pytest.fixture
def browser(
    client: TestClient, google: FakeGoogle, vendor: FakeLlm
) -> TestClient:
    """
    The student signed in on a browser, with a key saved.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :return: The browser.
    :rtype: TestClient
    """
    sign_in(client, google, STUDENT)
    body = {"vendor": "claude", "key": SECRET_KEY}
    assert client.put(KEY_ROUTE, json=body, headers=OWN_PAGE).status_code == 200
    vendor.used.clear()
    return client


async def person_id(
    session: AsyncSession, who: ColumnElement[bool]
) -> uuid.UUID | None:
    """
    Find one person.

    :param session: Database session.
    :type session: AsyncSession
    :param who: Which person.
    :type who: ColumnElement[bool]
    :return: Their id, if they exist.
    :rtype: uuid.UUID | None
    """
    query = select(User.id).where(who)
    return (await session.execute(query)).scalar_one_or_none()


async def add_job(
    make_session: async_sessionmaker,
    owner_email: str,
    status: str,
    files: dict[str, str],
    **fields: Any,
) -> Job:
    """
    A job that has reached this status, with its files uploaded.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param owner_email: Who owns it; nobody, for an address not in use.
    :type owner_email: str
    :param status: Its status.
    :type status: str
    :param files: Uploaded files: name -> text.
    :type files: dict[str, str]
    :param fields: Other columns.
    :type fields: Any
    :return: The job.
    :rtype: Job
    """
    async with make_session() as session:
        owner = await person_id(session, User.email == owner_email)
        run = Run(
            owner_id=owner,
            session_id=f"ai_{uuid.uuid4().hex[:8]}",
            target_id=HOUSE_TARGET_ID,
        )
        session.add(run)
        await session.flush()
        cards = [
            {"path": name, "size_bytes": len(text), "uploaded": True}
            for name, text in files.items()
        ]
        job = Job(
            script_name="toy_opt",
            node_key="step_one",
            status=status,
            run_id=run.id,
            owner_id=owner,
            parameters={"temp": 300.0, "pipeline_id": run.session_id},
            output_files=cards,
            **fields,
        )
        session.add(job)
        await session.commit()
    store = atomfield.state.store
    for name, text in files.items():
        key = job_file_key(job.run_id, job.id, name)
        await store.write(key, text.encode("utf-8"))
    return job


def failed_job(make_session: async_sessionmaker, **fields: Any) -> Job:
    """
    The student's failed job, with a log.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param fields: Other columns.
    :type fields: Any
    :return: The job.
    :rtype: Job
    """
    files = {"toy_opt.log": LOG}
    return asyncio.run(
        add_job(make_session, STUDENT.email, JobStatus.FAILED, files, **fields)
    )


def reviews_route(job: Job) -> str:
    """
    A job's reviews.

    :param job: The job.
    :type job: Job
    :return: The route.
    :rtype: str
    """
    return f"/api/jobs/{job.id}/ai-reviews"


def press(browser: TestClient, job: Job) -> dict[str, Any]:
    """
    Press the button. The test client answers once the background work
    has finished, so what the review came to can be read straight after.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param job: The job.
    :type job: Job
    :return: The stored review.
    :rtype: dict[str, Any]
    """
    answer = browser.post(reviews_route(job), headers=OWN_PAGE)
    assert answer.status_code == 202, answer.text
    return browser.get(f"{reviews_route(job)}/latest").json()


async def add_review(
    make_session: async_sessionmaker,
    job: Job,
    age: timedelta = timedelta(0),
) -> uuid.UUID:
    """
    A review already running, started some time ago.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param job: Its job.
    :type job: Job
    :param age: How long ago it started.
    :type age: timedelta
    :return: The review's id.
    :rtype: uuid.UUID
    """
    async with make_session() as session:
        review = AiReview(
            job_id=job.id,
            requested_by=job.owner_id,
            kind="fix",
            status=ReviewStatus.RUNNING,
            vendor="claude",
            model="some-model",
            created_at=datetime.now(UTC) - age,
        )
        session.add(review)
        await session.commit()
        return review.id


def test_a_failed_step_gets_a_fix_with_the_persons_key_and_model(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The whole click: the answer is kept, and shows who answered and what
    it cost in tokens.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    review = press(browser, job)
    assert review["kind"] == "fix"
    assert review["status"] == "done"
    assert review["summary"] == ANSWER["summary"]
    assert review["explanation"] == ANSWER["explanation"]
    assert review["check_next"] == ANSWER["check_next"]
    assert review["vendor"] == "claude"
    assert review["model"] == "some-model"
    assert review["answered_by"] == "model-that-answered"
    assert (review["input_tokens"], review["output_tokens"]) == (5, 6)
    assert review["finished_at"]
    assert vendor.used == [(AiVendor.CLAUDE, SECRET_KEY)]
    assert vendor.questions[0].model == "some-model"
    assert "failed" in vendor.questions[0].system
    assert SECRET_KEY not in json.dumps(review)


def test_a_finished_step_gets_an_analysis(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The kind follows from how the step ended, not from the request.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    files = {"a_optimized.xyz": "1\nresult\nH 0 0 0\n"}
    job = asyncio.run(
        add_job(make_session, STUDENT.email, JobStatus.SUCCEEDED, files)
    )
    review = press(browser, job)
    assert review["kind"] == "analysis"
    assert "finished" in vendor.questions[0].system


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.WAITING,
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.CANCELLED,
        JobStatus.UPSTREAM_FAILED,
    ],
)
def test_a_step_that_didnt_finish_or_fail_is_refused(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    status: JobStatus,
):
    """
    Still going, cancelled, or never run: nothing to review, nothing paid.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param status: The job's status.
    :type status: JobStatus
    """
    job = asyncio.run(add_job(make_session, STUDENT.email, status, {}))
    answer = browser.post(reviews_route(job), headers=OWN_PAGE)
    assert answer.status_code == 409
    assert vendor.used == []


def test_suggestions_are_checked_and_a_made_up_one_is_flagged(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    The stored answer says which suggestion is real, with its current
    value, and which the model made up.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    good, made_up = press(browser, failed_job(make_session))["suggestions"]
    assert good["setting"] == "temp"
    assert good["current"] == 300.0
    assert good["value"] == "350"
    assert good["unit"] == "K"
    assert good["problem"] is None
    assert made_up["setting"] == "smearing_x"
    assert made_up["problem"] == NOT_A_SETTING


def test_what_was_sent_can_be_read_and_holds_no_key(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The person can read the exact text; it is what the model got; and the
    job file routes can't reach it.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session, error_message="it broke")
    review = press(browser, job)
    assert review["read_parts"] == [{"name": "toy_opt.log", "shown": "all"}]
    route = f"{reviews_route(job)}/{review['id']}/sent"
    sent = browser.get(route)
    assert sent.status_code == 200
    assert sent.headers["x-content-type-options"] == "nosniff"
    assert sent.text == vendor.questions[0].user
    assert "the real error is here" in sent.text
    assert "Error: it broke" in sent.text
    assert SECRET_KEY not in sent.text
    other = failed_job(make_session)
    wrong_job = f"{reviews_route(other)}/{review['id']}/sent"
    assert browser.get(wrong_job).status_code == 404
    file_route = f"/api/jobs/{job.id}/files/{review['id']}.txt"
    assert browser.get(file_route).status_code == 404


def test_a_task_s_pages_are_read_and_listed(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    With pages listed, the matching parts are sent and named; a page that
    can't be read is named too.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param monkeypatch: Lists pages for the toy task.
    :type monkeypatch: pytest.MonkeyPatch
    """
    pages = [
        ReferencePage(title="QE guide", page="docs/quantum-espresso.md"),
        ReferencePage(title="Gone", page="docs/no-such-guide.md"),
    ]
    monkeypatch.setattr(Catalog, "pages_for", lambda self, task_id: pages)
    job = failed_job(make_session, error_message="trouble with magnetization")
    review = press(browser, job)
    assert {"name": "QE guide", "shown": "matching parts"} in (
        review["read_parts"]
    )
    assert review["unread_pages"] == ["Gone"]
    assert "magnetization" in vendor.questions[0].user


@pytest.mark.parametrize(
    ("error", "message"),
    [(KEY_REFUSED, KEY_REFUSED), (OVER_LIMIT, OVER_LIMIT)],
)
def test_a_vendors_refusal_becomes_a_plain_failed_review(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    error: str,
    message: str,
):
    """
    The review ends as failed and says what to do. The text that was sent
    is still there to read.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param error: What the vendor's client raises.
    :type error: str
    :param message: What the person sees.
    :type message: str
    """
    vendor.error = LlmError(error)
    job = failed_job(make_session)
    review = press(browser, job)
    assert review["status"] == "failed"
    assert review["error"] == message
    assert review["summary"] is None
    route = f"{reviews_route(job)}/{review['id']}/sent"
    assert browser.get(route).status_code == 200


def test_a_reply_that_cant_be_read_says_so(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    A reply outside the shape is not shown as if it were an answer.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    vendor.reply = reply_of('{"summary": "only this"}')
    review = press(browser, failed_job(make_session))
    assert review["status"] == "failed"
    assert review["error"] == UNREADABLE


def test_a_step_with_nothing_to_read_costs_nothing(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    No files and no error: the vendor isn't called, so nothing is paid.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = asyncio.run(
        add_job(make_session, STUDENT.email, JobStatus.FAILED, {})
    )
    review = press(browser, job)
    assert review["status"] == "failed"
    assert review["error"] == NOTHING_TO_READ
    assert vendor.questions == []
    route = f"{reviews_route(job)}/{review['id']}/sent"
    assert browser.get(route).status_code == 404


def test_a_lost_agents_error_alone_is_worth_asking_about(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    A step the server failed may have no files, only its reason.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = asyncio.run(
        add_job(
            make_session,
            STUDENT.email,
            JobStatus.FAILED,
            {},
            error_message="Its agent went silent",
        )
    )
    assert press(browser, job)["status"] == "done"
    assert "Its agent went silent" in vendor.questions[0].user


def test_asking_again_makes_a_new_review(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    An answer stays until someone asks again, which is a new paid call.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    first = press(browser, job)
    assert (
        browser.get(f"{reviews_route(job)}/latest").json()["id"]
        == (first["id"])
    )
    assert len(vendor.questions) == 1
    second = press(browser, job)
    assert second["id"] != first["id"]
    assert len(vendor.questions) == 2


def test_a_second_click_while_one_runs_gets_the_same_review(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    A double click can't pay twice.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    running = asyncio.run(add_review(make_session, job))
    answer = browser.post(reviews_route(job), headers=OWN_PAGE)
    assert answer.status_code == 202
    assert answer.json()["id"] == str(running)
    assert answer.json()["status"] == "running"
    assert vendor.used == []


def test_a_review_lost_with_its_server_clears_itself(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    It reads as failed, so the tab stops waiting, and the next click marks
    it so and starts a new one.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    lost = asyncio.run(add_review(make_session, job, timedelta(minutes=11)))
    seen = browser.get(f"{reviews_route(job)}/latest").json()
    assert seen["id"] == str(lost)
    assert seen["status"] == "failed"
    assert seen["error"] == INTERRUPTED
    new = press(browser, job)
    assert new["id"] != str(lost)
    assert new["status"] == "done"
    assert len(vendor.questions) == 1


def test_a_recent_running_review_keeps_running(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    Only a review too old to be alive reads as lost.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    asyncio.run(add_review(make_session, job, timedelta(minutes=1)))
    seen = browser.get(f"{reviews_route(job)}/latest").json()
    assert seen["status"] == "running"


def test_a_step_with_no_review_says_so(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    The tab offers the button.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    seen = browser.get(f"{reviews_route(job)}/latest")
    assert seen.status_code == 200
    assert seen.json() is None


def test_with_no_key_or_no_secret_the_click_is_refused(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    Each says why, and nothing reaches the vendor.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    atomfield.dependency_overrides[get_key_vault] = lambda: None
    try:
        no_secret = browser.post(reviews_route(job), headers=OWN_PAGE)
    finally:
        del atomfield.dependency_overrides[get_key_vault]
    assert no_secret.status_code == 409
    assert no_secret.json()["detail"] == NO_SECRET_MESSAGE
    browser.delete(KEY_ROUTE, headers=OWN_PAGE)
    no_key = browser.post(reviews_route(job), headers=OWN_PAGE)
    assert no_key.status_code == 409
    assert no_key.json()["detail"] == NO_KEY_MESSAGE
    assert vendor.questions == []


def test_a_changed_server_secret_fails_plainly(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    A key sealed under an old secret can't be used, and the person is told
    to add it again.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    atomfield.dependency_overrides[get_key_vault] = lambda: KeyVault("other")
    try:
        review = press(browser, job)
    finally:
        del atomfield.dependency_overrides[get_key_vault]
    assert review["status"] == "failed"
    assert review["error"] == SECRET_CHANGED
    assert vendor.questions == []


def test_too_many_clicks_are_turned_back(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Each click can cost money, so a limit stops a stuck one.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param monkeypatch: Lowers the limit.
    :type monkeypatch: pytest.MonkeyPatch
    """
    job = failed_job(make_session)
    monkeypatch.setattr(settings, "AI_CALLS_PER_MINUTE", 0)
    answer = browser.post(reviews_route(job), headers=OWN_PAGE)
    assert answer.status_code == 429
    assert vendor.questions == []


def test_someone_elses_job_doesnt_exist_for_you(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    Another person's step can't be reviewed or read.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    files = {"toy_opt.log": LOG}
    job = asyncio.run(add_job(make_session, NOBODY, JobStatus.FAILED, files))
    route = reviews_route(job)
    assert browser.post(route, headers=OWN_PAGE).status_code == 404
    assert browser.get(f"{route}/latest").status_code == 404


def test_a_script_key_cant_spend_a_persons_ai_key(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
    make_session: async_sessionmaker,
):
    """
    A leaked script key can't start reviews or read them.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Makes a person with a script key.
    :type make_user_headers: UserHeadersFactory
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    client.cookies.clear()
    label = f"script_{uuid.uuid4().hex[:8]}"
    headers = make_user_headers(label)

    async def own_job() -> Job:
        """
        A job the script key's own person owns, so that the refusal can
        only be about the key.

        :return: The job.
        :rtype: Job
        """
        job = await add_job(make_session, NOBODY, JobStatus.FAILED, {})
        async with make_session() as session:
            owner = await person_id(session, User.name == label)
            await session.execute(
                update(Job).where(Job.id == job.id).values(owner_id=owner)
            )
            await session.commit()
        return job

    route = reviews_route(asyncio.run(own_job()))
    assert client.post(route, headers=headers).status_code == 403
    assert client.get(f"{route}/latest", headers=headers).status_code == 403


def test_deleting_a_run_deletes_its_reviews_and_what_was_sent(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    Nothing about a review outlives its run.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    review_id = uuid.UUID(press(browser, job)["id"])
    store = atomfield.state.store
    key = ai_sent_key(job.run_id, review_id)
    assert asyncio.run(store.read(key)) is not None

    async def delete_it() -> AiReview | None:
        """
        Delete the run, and look for its review.

        :return: The review, if it is still there.
        :rtype: AiReview | None
        """
        async with make_session() as session:
            await delete_runs(session, store, [job.run_id])
            return await session.get(AiReview, review_id)

    assert asyncio.run(delete_it()) is None
    assert asyncio.run(store.read(key)) is None


def direct_runner(
    make_session: async_sessionmaker, vendor: FakeLlm
) -> ReviewRunner:
    """
    A runner on the test's own connections, to run a review outside a
    request.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :return: The runner.
    :rtype: ReviewRunner
    """
    state = atomfield.state
    library = PageLibrary(state.store, state.http)
    return ReviewRunner(
        make_session,
        state.catalogs,
        EvidenceCollector(state.store, library),
        state.store,
        KeyVault(settings.AI_KEY_SECRET),
        vendor.factory(),
    )


async def read_review(
    make_session: async_sessionmaker, review_id: uuid.UUID
) -> AiReview:
    """
    A review as stored.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param review_id: The review.
    :type review_id: uuid.UUID
    :return: The review.
    :rtype: AiReview
    """
    async with make_session() as session:
        return await session.get(AiReview, review_id)


def test_a_key_removed_before_the_work_starts_is_said_plainly(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    Removing a key while a review is on its way stops it being used.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    review_id = asyncio.run(add_review(make_session, job))
    browser.delete(KEY_ROUTE, headers=OWN_PAGE)
    runner = direct_runner(make_session, vendor)
    asyncio.run(runner.run(review_id))
    review = asyncio.run(read_review(make_session, review_id))
    assert review.status == ReviewStatus.FAILED
    assert review.error == KEY_GONE
    assert vendor.questions == []


def test_a_call_that_runs_too_long_is_stopped(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Every wait has a bound, and its end is a plain message.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param monkeypatch: Shortens the limit, and slows the vendor.
    :type monkeypatch: pytest.MonkeyPatch
    """

    async def slowly(question: Any) -> LlmReply:
        """
        Take far longer than the limit.

        :param question: The question, unused.
        :type question: Any
        :return: Never returns in time.
        :rtype: LlmReply
        """
        await asyncio.sleep(30)
        return reply_of()

    monkeypatch.setattr(reviews_module, "CALL_LIMIT_SECONDS", 0.2)
    monkeypatch.setattr(vendor, "ask", slowly)
    job = failed_job(make_session)
    review_id = asyncio.run(add_review(make_session, job))
    asyncio.run(direct_runner(make_session, vendor).run(review_id))
    review = asyncio.run(read_review(make_session, review_id))
    assert review.status == ReviewStatus.FAILED
    assert review.error == TOO_SLOW


def test_an_unexpected_error_is_recorded_and_raised(
    browser: TestClient,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A bug doesn't leave the tab spinning, and still reaches the log.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param monkeypatch: Breaks the vendor.
    :type monkeypatch: pytest.MonkeyPatch
    """

    async def broken(question: Any) -> LlmReply:
        """
        Fail in a way nothing expects.

        :param question: The question, unused.
        :type question: Any
        :return: Never returns.
        :rtype: LlmReply
        :raises ZeroDivisionError: Always.
        """
        raise ZeroDivisionError

    monkeypatch.setattr(vendor, "ask", broken)
    job = failed_job(make_session)
    review_id = asyncio.run(add_review(make_session, job))
    runner = direct_runner(make_session, vendor)
    with pytest.raises(ZeroDivisionError):
        asyncio.run(runner.run(review_id))
    review = asyncio.run(read_review(make_session, review_id))
    assert review.status == ReviewStatus.FAILED
    assert review.error == SOMETHING_WRONG


def test_a_late_answer_cant_overwrite_a_review_marked_lost(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    Only a running review changes.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    job = failed_job(make_session)
    review_id = asyncio.run(add_review(make_session, job))
    runner = direct_runner(make_session, vendor)

    async def mark_lost() -> None:
        """
        Mark the review as lost, as the next click would.
        """
        statement = (
            update(AiReview)
            .where(AiReview.id == review_id)
            .values(status=ReviewStatus.FAILED, error=INTERRUPTED)
        )
        async with make_session() as session:
            await session.execute(statement)
            await session.commit()

    asyncio.run(mark_lost())
    asyncio.run(runner.record(review_id, {"status": ReviewStatus.DONE}))
    review = asyncio.run(read_review(make_session, review_id))
    assert review.status == ReviewStatus.FAILED
    assert review.error == INTERRUPTED


def test_the_summaries_of_the_steps_before_reach_the_model(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The job's parents come from the run's own edges.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    parent = asyncio.run(
        add_job(
            make_session,
            STUDENT.email,
            JobStatus.SUCCEEDED,
            {"a_summary.txt": "Fermi energy 6.2 eV"},
        )
    )
    job = failed_job(make_session)

    async def link() -> None:
        """
        Make the parent the step before the job.
        """
        async with make_session() as session:
            session.add(
                JobDependency(upstream_id=parent.id, downstream_id=job.id)
            )
            await session.commit()

    asyncio.run(link())
    press(browser, job)
    assert "Fermi energy 6.2 eV" in vendor.questions[0].user


def test_the_stored_key_is_only_read_never_changed(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    A review leaves the key as it was.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """

    async def stored_keys() -> list[str]:
        """
        Every stored key, encrypted.

        :return: The stored values.
        :rtype: list[str]
        """
        async with make_session() as session:
            rows = await session.execute(select(AiKey.sealed_key))
            return sorted(rows.scalars())

    before = asyncio.run(stored_keys())
    press(browser, failed_job(make_session))
    assert asyncio.run(stored_keys()) == before
