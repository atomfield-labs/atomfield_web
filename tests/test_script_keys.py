"""
Keys for scripts: made, listed and revoked by a person signed in on
the web app. A key itself can do none of that, so revoking a leaked
key really ends it.
"""

from fastapi.testclient import TestClient

from tests.browser import (
    LOGOUT,
    MY_ACCOUNT,
    OWN_PAGE,
    PRINCIPAL,
    STUDENT,
    sign_in,
)
from tests.conftest import UserHeadersFactory
from tests.fake_google import FakeGoogle

KEYS = "/api/auth/me/keys"


def make_key(client: TestClient, label: str = "laptop") -> dict:
    """
    Make a key from the web app, signed in.

    :param client: In-process API client, a signed-in browser.
    :type client: TestClient
    :param label: What the key is for.
    :type label: str
    :return: The new key, with its secret.
    :rtype: dict
    """
    made = client.post(KEYS, json={"label": label}, headers=OWN_PAGE)
    assert made.status_code == 201
    return made.json()


def listed_ids(client: TestClient) -> list[str]:
    """
    The ids of the signed-in person's working keys.

    :param client: In-process API client, a signed-in browser.
    :type client: TestClient
    :return: Key ids, newest first.
    :rtype: list[str]
    """
    return [key["id"] for key in client.get(KEYS).json()]


def test_a_signed_in_person_makes_uses_and_revokes_a_key(
    client: TestClient, google: FakeGoogle
):
    """
    A key made in the web app works for that person's scripts until
    they revoke it; then it stops at once.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    made = make_key(client)
    script = {"X-API-Key": made["api_key"]}
    as_script = client.get(MY_ACCOUNT, headers=script).json()
    assert made["id"] in listed_ids(client)
    assert as_script["email"] == STUDENT.email
    revoked = client.delete(f"{KEYS}/{made['id']}", headers=OWN_PAGE)
    assert revoked.status_code == 204
    assert client.get(MY_ACCOUNT, headers=script).status_code == 401
    assert made["id"] not in listed_ids(client)


def test_a_key_cannot_make_or_see_keys(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    A script's key can neither make new keys nor list the others.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    script = make_user_headers()
    made = client.post(KEYS, json={}, headers=script).status_code
    listed = client.get(KEYS, headers=script).status_code
    assert (made, listed) == (403, 403)


def test_nobody_revokes_someone_elses_key(
    client: TestClient, google: FakeGoogle
):
    """
    Another person cannot revoke your key, nor learn it exists: the
    answer is the same as for no key at all.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    sign_in(client, google, STUDENT)
    theirs = make_key(client)
    client.post(LOGOUT, headers=OWN_PAGE)
    sign_in(client, google, PRINCIPAL)
    refused = client.delete(f"{KEYS}/{theirs['id']}", headers=OWN_PAGE)
    still_works = {"X-API-Key": theirs["api_key"]}
    assert refused.status_code == 404
    assert client.get(MY_ACCOUNT, headers=still_works).status_code == 200
