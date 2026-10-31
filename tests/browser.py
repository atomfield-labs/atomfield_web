"""
A browser signing in to AtomField through the fake Google: the
institute's test accounts, the settings that point sign-in at the
fake, and the steps a browser takes.
"""

import httpx
from fastapi.testclient import TestClient

from app.api.routes.auth import SIGN_IN_ERROR
from tests.fake_google import (
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    REDIRECT_URI,
    Account,
    FakeGoogle,
    query_of,
)

INSTITUTE = "institute.ac.in"
LOGIN = "/api/auth/login"
CALLBACK = "/api/auth/callback"
LOGOUT = "/api/auth/logout"
MY_ACCOUNT = "/api/auth/me"
# What the browser says on requests from AtomField's own pages.
OWN_PAGE = {"Origin": "http://testserver"}
STUDENT = Account(email=f"ada@{INSTITUTE}")
OWNER = Account(email=f"grace@{INSTITUTE}", name="Grace Hopper")
SIGN_IN_SETTINGS = {
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": CLIENT_ID,
    "OIDC_CLIENT_SECRET": CLIENT_SECRET,
    "OIDC_REDIRECT_URI": REDIRECT_URI,
    "OWNER_EMAILS": OWNER.email,
}


def sign_in(
    client: TestClient, google: FakeGoogle, account: Account
) -> httpx.Response:
    """
    Go through the whole sign-in, as a browser would.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param account: Who signs in at Google.
    :type account: Account
    :return: The answer to Google sending the browser back.
    :rtype: httpx.Response
    """
    login = client.get(LOGIN, follow_redirects=False)
    answer = google.consent(login.headers["location"], account)
    return client.get(CALLBACK, params=answer, follow_redirects=False)


def problem_in(response: httpx.Response) -> str | None:
    """
    What the web app is told went wrong, if anything.

    :param response: A redirect, to the web app or to Google.
    :type response: httpx.Response
    :return: The problem, or None.
    :rtype: str | None
    """
    return query_of(response.headers["location"]).get(SIGN_IN_ERROR)
