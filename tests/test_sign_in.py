"""
Signing in with an institute Google account, against a fake Google:
who gets in, how a signed-in browser is known afterwards, and what
another site cannot make it do.
"""

import asyncio
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routes.auth import SIGN_IN_COOKIE
from app.core.config import settings
from app.core.security import SESSION_COOKIE
from app.main import app, create_sign_in
from app.models.user import User
from app.sign_in.provider import SignInStart
from app.sign_in.refusals import SignInProblem
from tests.browser import (
    CALLBACK,
    INSTITUTE,
    LOGIN,
    LOGOUT,
    MY_ACCOUNT,
    OWN_PAGE,
    PRINCIPAL,
    SIGN_IN_SETTINGS,
    STUDENT,
    problem_in,
    sign_in,
)
from tests.fake_google import Account, FakeGoogle, new_key, query_of

CLEAR_JOBS = "/api/jobs/clear"
# Another page on the institute's domain: the same site, as browsers
# count sites, so the session cookie goes along.
SIBLING_PAGE = {"Origin": f"https://students.{INSTITUTE}"}
# RFC 7636, appendix B.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


async def set_active(
    make_session: async_sessionmaker, email: str, active: bool
) -> None:
    """
    Turn a person's account off or on, as the administrator would.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param email: The person's email.
    :type email: str
    :param active: On or off.
    :type active: bool
    """
    change = update(User).where(User.email == email)
    async with make_session() as session:
        await session.execute(change.values(is_active=active))
        await session.commit()


def test_an_institute_account_signs_in(client: TestClient, google: FakeGoogle):
    """
    A verified account the institute runs signs in. The browser is
    then known by its cookie, which page scripts cannot read and other
    sites' requests do not carry.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    finished = sign_in(client, google, STUDENT)
    shown = client.get(MY_ACCOUNT).json()
    cookies = finished.headers.get_list("set-cookie")
    session = next(line for line in cookies if line.startswith(SESSION_COOKIE))
    assert finished.headers["location"] == "/"
    assert (shown["email"], shown["label"]) == (STUDENT.email, STUDENT.name)
    assert not shown["is_admin"]
    assert "httponly" in session.lower()
    assert "samesite=lax" in session.lower()


@pytest.mark.parametrize(
    ("account", "problem"),
    [
        (Account("ada@gmail.com", None), SignInProblem.OUTSIDE),
        (Account(f"ada@{INSTITUTE}", None), SignInProblem.OUTSIDE),
        (Account("ada@other.ac.in", "other.ac.in"), SignInProblem.OUTSIDE),
        (
            Account(f"ada@{INSTITUTE}", INSTITUTE, verified=False),
            SignInProblem.FAILED,
        ),
    ],
    ids=["personal", "personal-with-our-address", "other", "unverified"],
)
def test_only_the_institutes_own_accounts_get_in(
    client: TestClient,
    google: FakeGoogle,
    account: Account,
    problem: SignInProblem,
):
    """
    Personal accounts, even one made with an institute address, other
    institutes' accounts and unverified addresses are turned away.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param account: Who tries to sign in.
    :type account: Account
    :param problem: What the web app should be told.
    :type problem: SignInProblem
    """
    finished = sign_in(client, google, account)
    assert problem_in(finished) == problem
    assert SESSION_COOKIE not in client.cookies


def test_a_sign_in_finishes_only_in_the_browser_that_started_it(
    client: TestClient, google: FakeGoogle
):
    """
    Someone who starts a sign-in with their own account cannot get
    another person's browser to finish it: that browser lacks the
    sign-in's cookie, so nobody is signed in there.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    login = client.get(LOGIN, follow_redirects=False)
    answer = google.consent(login.headers["location"], STUDENT)
    client.cookies.clear()
    finished = client.get(CALLBACK, params=answer, follow_redirects=False)
    assert problem_in(finished) == SignInProblem.EXPIRED
    assert SESSION_COOKIE not in client.cookies


def test_a_sign_in_cannot_be_finished_twice(
    client: TestClient, google: FakeGoogle
):
    """
    Google's answer works once: replayed, even with the sign-in's
    cookie, it is refused.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    login = client.get(LOGIN, follow_redirects=False)
    answer = google.consent(login.headers["location"], STUDENT)
    client.get(CALLBACK, params=answer, follow_redirects=False)
    replay = {"Cookie": f"{SIGN_IN_COOKIE}={answer['state']}"}
    replayed = client.get(
        CALLBACK, params=answer, headers=replay, follow_redirects=False
    )
    assert problem_in(replayed) == SignInProblem.EXPIRED


def test_saying_no_at_google_signs_nobody_in(
    client: TestClient, google: FakeGoogle
):
    """
    Declining on Google's page brings the person back, signed out.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    login = client.get(LOGIN, follow_redirects=False)
    answer = google.decline(login.headers["location"])
    finished = client.get(CALLBACK, params=answer, follow_redirects=False)
    assert problem_in(finished) == SignInProblem.DENIED
    assert SESSION_COOKIE not in client.cookies


@pytest.mark.parametrize(
    "checks_pkce", [True, False], ids=["pkce", "nonce-alone"]
)
def test_an_answer_for_another_sign_in_is_refused(
    client: TestClient, google: FakeGoogle, checks_pkce: bool
):
    """
    Google's answer to one sign-in, brought back under another's
    state, is refused. PKCE stops it; so does the nonce, should a
    provider not check PKCE.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param checks_pkce: Whether the fake Google checks PKCE.
    :type checks_pkce: bool
    """
    google.checks_pkce = checks_pkce
    first = client.get(LOGIN, follow_redirects=False)
    second = client.get(LOGIN, follow_redirects=False)
    answer = google.consent(first.headers["location"], STUDENT)
    answer["state"] = query_of(second.headers["location"])["state"]
    finished = client.get(CALLBACK, params=answer, follow_redirects=False)
    assert problem_in(finished) == SignInProblem.FAILED
    assert SESSION_COOKIE not in client.cookies


def test_a_token_signed_by_anyone_but_google_is_refused(
    client: TestClient, google: FakeGoogle
):
    """
    An ID token signed with a key Google does not publish is refused.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    google.signing_key = new_key()
    finished = sign_in(client, google, STUDENT)
    assert problem_in(finished) == SignInProblem.FAILED


def test_a_token_meant_for_another_app_is_refused(
    client: TestClient, google: FakeGoogle
):
    """
    A genuine ID token, but for another app, is refused: otherwise any
    app a person signs in to could sign in here as them.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    google.audience = "another-app.apps.googleusercontent.com"
    finished = sign_in(client, google, STUDENT)
    assert problem_in(finished) == SignInProblem.FAILED


def test_listed_people_sign_in_as_administrators(
    client: TestClient, google: FakeGoogle
):
    """
    A person in ``ADMIN_EMAILS`` is an administrator once signed in.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, PRINCIPAL)
    assert client.get(MY_ACCOUNT).json()["is_admin"]


def test_a_turned_off_account_is_shut_out(
    client: TestClient,
    google: FakeGoogle,
    make_session: async_sessionmaker,
):
    """
    Turning an account off stops its signed-in browser at once, and
    stops it signing in again.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    sign_in(client, google, STUDENT)
    asyncio.run(set_active(make_session, STUDENT.email, False))
    stopped = client.get(MY_ACCOUNT).status_code
    again = sign_in(client, google, STUDENT)
    asyncio.run(set_active(make_session, STUDENT.email, True))
    assert stopped == 401
    assert problem_in(again) == SignInProblem.DISABLED


def test_signing_out_ends_the_session_on_the_server(
    client: TestClient, google: FakeGoogle
):
    """
    After signing out, the session's secret is worthless, even if a
    copy of the cookie survives somewhere.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    copy = {"Cookie": f"{SESSION_COOKIE}={client.cookies[SESSION_COOKIE]}"}
    signed_out = client.post(LOGOUT, headers=OWN_PAGE)
    assert signed_out.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert client.get(MY_ACCOUNT, headers=copy).status_code == 401


def test_another_page_cannot_act_for_a_signed_in_browser(
    client: TestClient, google: FakeGoogle
):
    """
    A page elsewhere on the institute's domain gets the cookie sent
    along, but cannot change anything: only AtomField's own pages can.
    Reading needs no such check (the test client sends no Origin).

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    sibling = client.delete(CLEAR_JOBS, headers=SIBLING_PAGE).status_code
    unmarked = client.delete(CLEAR_JOBS).status_code
    own = client.delete(CLEAR_JOBS, headers=OWN_PAGE).status_code
    assert (sibling, unmarked, own) == (403, 403, 200)
    assert client.get(MY_ACCOUNT).status_code == 200


def test_a_flood_of_sign_ins_from_one_address_is_turned_back(
    client: TestClient,
    google: FakeGoogle,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Past the per-minute limit, an address is sent back to the web app
    with a reason instead of to Google, so a flood of starts cannot
    fill Redis with sign-ins nobody finishes.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param monkeypatch: Lowers the limit and trusts the proxy header.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(settings, "SIGN_IN_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    address = {"CF-Connecting-IP": f"203.0.113.{uuid.uuid4().int % 250 + 1}"}
    starts = [
        client.get(LOGIN, headers=address, follow_redirects=False)
        for _ in range(3)
    ]
    problems = [problem_in(start) for start in starts]
    assert problems == [None, None, SignInProblem.BUSY]


def test_without_sign_in_set_up_the_web_app_is_told(client: TestClient):
    """
    A server with no sign-in set up (as in these tests' settings)
    sends the browser back with a reason, not to a provider.

    :param client: In-process API client.
    :type client: TestClient
    """
    login = client.get(LOGIN, follow_redirects=False)
    assert problem_in(login) == SignInProblem.UNAVAILABLE


def test_half_set_up_sign_in_stops_the_server(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    With a client id but no institute domain, the server refuses to
    start rather than fail at someone's first sign-in.

    :param client: In-process API client.
    :type client: TestClient
    :param monkeypatch: Sets the sign-in settings for this test.
    :type monkeypatch: pytest.MonkeyPatch
    """
    for name, value in SIGN_IN_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "SIGN_IN_DOMAINS", "")
    with pytest.raises(RuntimeError, match="SIGN_IN_DOMAINS"):
        create_sign_in(httpx.AsyncClient(), app.state.redis)


def test_the_pkce_challenge_is_the_standards():
    """
    The server's PKCE challenge matches RFC 7636's worked example.
    """
    start = SignInStart(state="", nonce="", verifier=RFC_VERIFIER)
    assert start.challenge == RFC_CHALLENGE
