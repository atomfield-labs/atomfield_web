"""
A person's own key for an AI vendor: checked, encrypted, and never shown
again. Only a signed-in browser can manage one.
"""

import asyncio
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.vault import KeyUnreadableError, KeyVault
from app.ai.vendors import (
    FREE_GEMINI_WARNING,
    KEY_REFUSED,
    AiVendor,
    LlmError,
)
from app.api.dependencies import get_key_vault, get_llm_factory
from app.api.routes.ai import NO_SECRET_MESSAGE, SECRET_CHANGED_MESSAGE
from app.core.config import settings
from app.main import app
from app.models.ai import AiKey
from app.models.user import User
from tests.browser import OWN_PAGE, STUDENT, sign_in
from tests.conftest import UserHeadersFactory
from tests.fake_google import FakeGoogle
from tests.fake_vendors import FakeLlm

KEY_ROUTE = "/api/ai/key"
MODELS_ROUTE = "/api/ai/key/models"
SECRET_KEY = "sk-test-key-that-must-never-show-1234"
ENDING = SECRET_KEY[-4:]
CLAUDE_BODY = {"vendor": "claude", "key": SECRET_KEY}


@pytest.fixture
def vendor(client: TestClient) -> Iterator[FakeLlm]:
    """
    A fake vendor in place of the real ones.

    :param client: In-process API client.
    :type client: TestClient
    :return: The fake.
    :rtype: Iterator[FakeLlm]
    """
    fake = FakeLlm(models=["claude-opus-5-5", "claude-sonnet-5-5"])
    app.dependency_overrides[get_llm_factory] = fake.factory
    yield fake
    del app.dependency_overrides[get_llm_factory]


@pytest.fixture
def browser(
    client: TestClient,
    google: FakeGoogle,
    vendor: FakeLlm,
    make_session: async_sessionmaker,
) -> TestClient:
    """
    The student signed in on a browser, with no key saved yet.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :return: The browser.
    :rtype: TestClient
    """
    sign_in(client, google, STUDENT)
    client.delete(KEY_ROUTE, headers=OWN_PAGE)
    return client


async def stored(make_session: async_sessionmaker) -> AiKey | None:
    """
    The student's key as the database holds it.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :return: The row, if any.
    :rtype: AiKey | None
    """
    async with make_session() as session:
        person = select(User.id).where(User.email == STUDENT.email)
        user_id: UUID = (await session.execute(person)).scalar_one()
        return await session.get(AiKey, user_id)


def test_it_starts_with_no_key_and_lists_the_vendors(browser: TestClient):
    """
    The web app learns the vendors, and that Gemini carries a warning.

    :param browser: The signed-in browser.
    :type browser: TestClient
    """
    state = browser.get(KEY_ROUTE).json()
    assert state["available"] is True
    assert state["saved"] is None
    by_id = {vendor["id"]: vendor for vendor in state["vendors"]}
    assert set(by_id) == {"claude", "openai", "gemini"}
    assert by_id["claude"]["title"] == "Claude"
    assert by_id["gemini"]["warning"] == FREE_GEMINI_WARNING
    assert by_id["claude"]["warning"] is None


def test_a_key_is_checked_encrypted_and_never_shown(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    Saving calls the vendor with the key, stores it encrypted, and no
    answer ever holds it: only its last four characters.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    answer = browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    assert answer.status_code == 200
    assert SECRET_KEY not in answer.text
    assert vendor.used == [(AiVendor.CLAUDE, SECRET_KEY)]
    body = answer.json()
    assert body["models"] == vendor.models
    assert body["saved"] == {
        "vendor": "claude",
        "model": "claude-opus-5-5",
        "key_ending": ENDING,
    }
    assert SECRET_KEY not in browser.get(KEY_ROUTE).text
    row = asyncio.run(stored(make_session))
    assert SECRET_KEY not in row.sealed_key
    vault = KeyVault(settings.AI_KEY_SECRET)
    assert vault.reveal(row.sealed_key) == SECRET_KEY


def test_spaces_around_a_pasted_key_are_dropped(
    browser: TestClient, vendor: FakeLlm
):
    """
    A key pasted with a line end still works.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    """
    body = {"vendor": "gemini", "key": f"  {SECRET_KEY}\n"}
    browser.put(KEY_ROUTE, json=body, headers=OWN_PAGE)
    assert vendor.used == [(AiVendor.GEMINI, SECRET_KEY)]


def test_a_key_the_vendor_refuses_is_not_saved(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The person is told, and nothing is stored.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    vendor.error = LlmError(KEY_REFUSED)
    answer = browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    assert answer.status_code == 400
    assert answer.json()["detail"] == KEY_REFUSED
    assert asyncio.run(stored(make_session)) is None


def test_saving_again_replaces_the_key(
    browser: TestClient, make_session: async_sessionmaker
):
    """
    One key each: the new vendor and key take the old one's place.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    other = {"vendor": "openai", "key": "sk-another-key-9876"}
    answer = browser.put(KEY_ROUTE, json=other, headers=OWN_PAGE)
    assert answer.json()["saved"]["vendor"] == "openai"
    assert answer.json()["saved"]["key_ending"] == "9876"
    row = asyncio.run(stored(make_session))
    vault = KeyVault(settings.AI_KEY_SECRET)
    assert vault.reveal(row.sealed_key) == "sk-another-key-9876"


def test_a_person_chooses_a_model_and_removes_the_key(
    browser: TestClient, vendor: FakeLlm, make_session: async_sessionmaker
):
    """
    The model menu comes from the vendor through the stored key; removing
    the key forgets it, and doing so twice is fine.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    assert browser.get(MODELS_ROUTE).json() == vendor.models
    assert vendor.used[-1] == (AiVendor.CLAUDE, SECRET_KEY)
    body = {"model": "claude-sonnet-5-5"}
    chosen = browser.patch(KEY_ROUTE, json=body, headers=OWN_PAGE)
    assert chosen.json()["saved"]["model"] == "claude-sonnet-5-5"
    assert browser.delete(KEY_ROUTE, headers=OWN_PAGE).status_code == 204
    assert browser.delete(KEY_ROUTE, headers=OWN_PAGE).status_code == 204
    assert asyncio.run(stored(make_session)) is None
    assert browser.get(KEY_ROUTE).json()["saved"] is None


@pytest.mark.parametrize(
    ("method", "route", "body"),
    [
        ("GET", MODELS_ROUTE, None),
        ("PATCH", KEY_ROUTE, {"model": "any"}),
    ],
)
def test_with_no_key_there_is_nothing_to_use(
    browser: TestClient, method: str, route: str, body: dict | None
):
    """
    Listing models or choosing one needs a saved key.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param method: The HTTP method.
    :type method: str
    :param route: The route.
    :type route: str
    :param body: The JSON body, if any.
    :type body: dict | None
    """
    answer = browser.request(method, route, json=body, headers=OWN_PAGE)
    assert answer.status_code == 404


def test_with_no_server_secret_keys_cant_be_saved(
    browser: TestClient, vendor: FakeLlm
):
    """
    The web app is told AI help is off, and no key reaches the vendor.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    """
    app.dependency_overrides[get_key_vault] = lambda: None
    try:
        assert browser.get(KEY_ROUTE).json()["available"] is False
        answer = browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    finally:
        del app.dependency_overrides[get_key_vault]
    assert answer.status_code == 409
    assert answer.json()["detail"] == NO_SECRET_MESSAGE
    assert vendor.used == []


def test_a_changed_server_secret_asks_for_the_key_again(browser: TestClient):
    """
    A key sealed under an old secret can't be read, and the person is
    told what to do rather than shown an error.

    :param browser: The signed-in browser.
    :type browser: TestClient
    """
    browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    app.dependency_overrides[get_key_vault] = lambda: KeyVault("another")
    try:
        answer = browser.get(MODELS_ROUTE)
    finally:
        del app.dependency_overrides[get_key_vault]
    assert answer.status_code == 409
    assert answer.json()["detail"] == SECRET_CHANGED_MESSAGE


def test_too_many_calls_are_turned_back_before_the_vendor(
    browser: TestClient, vendor: FakeLlm, monkeypatch: pytest.MonkeyPatch
):
    """
    Each call can cost the person money, so a limit stops a stuck click.

    :param browser: The signed-in browser.
    :type browser: TestClient
    :param vendor: The fake vendor.
    :type vendor: FakeLlm
    :param monkeypatch: Lowers the limit.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(settings, "AI_CALLS_PER_MINUTE", 0)
    answer = browser.put(KEY_ROUTE, json=CLAUDE_BODY, headers=OWN_PAGE)
    assert answer.status_code == 429
    assert vendor.used == []


@pytest.mark.parametrize(
    ("method", "route"),
    [
        ("GET", KEY_ROUTE),
        ("PUT", KEY_ROUTE),
        ("PATCH", KEY_ROUTE),
        ("DELETE", KEY_ROUTE),
        ("GET", MODELS_ROUTE),
    ],
)
def test_a_script_key_cant_touch_an_ai_key(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
    method: str,
    route: str,
):
    """
    A leaked script key can't read, replace or use a person's AI key.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Makes a person with a script key.
    :type make_user_headers: UserHeadersFactory
    :param method: The HTTP method.
    :type method: str
    :param route: The route.
    :type route: str
    """
    client.cookies.clear()
    headers = make_user_headers("script")
    body = CLAUDE_BODY if method == "PUT" else {"model": "any"}
    send_body = method in {"PUT", "PATCH"}
    answer = client.request(
        method, route, json=body if send_body else None, headers=headers
    )
    assert answer.status_code == 403


def test_nobody_signed_out_gets_in(client: TestClient):
    """
    Signed out, the routes answer 401.

    :param client: In-process API client.
    :type client: TestClient
    """
    client.cookies.clear()
    assert client.get(KEY_ROUTE).status_code == 401


def test_the_vault_refuses_what_another_secret_sealed():
    """
    The same secret reads a key back; another one can't.
    """
    sealed = KeyVault("one secret").seal(SECRET_KEY)
    assert SECRET_KEY not in sealed
    assert KeyVault("one secret").reveal(sealed) == SECRET_KEY
    with pytest.raises(KeyUnreadableError):
        KeyVault("another secret").reveal(sealed)
