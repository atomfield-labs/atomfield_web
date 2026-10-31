"""
A stand-in for Google's sign-in, in process: its discovery document,
its published keys, and a token endpoint that signs ID tokens with a
key made for the tests. ``consent`` and ``decline`` play the person on
Google's sign-in page.
"""

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.sign_in.provider import DISCOVERY_PATH

# AtomField as registered with the fake Google.
ISSUER = "https://accounts.google.test"
CLIENT_ID = "atomfield-tests.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"
REDIRECT_URI = "http://testserver/api/auth/callback"

AUTHORIZATION_PATH = "/auth"
TOKEN_PATH = "/token"
KEYS_PATH = "/certs"
KEY_ID = "test-key"
ALGORITHM = "RS256"
TOKEN_SECONDS = 3600
KEY_BITS = 2048
PUBLIC_EXPONENT = 65537


def new_key() -> rsa.RSAPrivateKey:
    """
    A fresh RSA key, of the kind Google signs ID tokens with.

    :return: The private key.
    :rtype: rsa.RSAPrivateKey
    """
    return rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT, key_size=KEY_BITS
    )


def pkce_challenge(verifier: str) -> str:
    """
    RFC 7636's S256 challenge, worked out here on its own so a mistake
    in the server's version cannot cancel itself out.

    :param verifier: The PKCE verifier.
    :type verifier: str
    :return: The challenge.
    :rtype: str
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def query_of(link: str) -> dict[str, str]:
    """
    The query of a link, one value per name.

    :param link: The link.
    :type link: str
    :return: Name -> value.
    :rtype: dict[str, str]
    """
    return dict(parse_qsl(urlsplit(link).query))


@dataclass(frozen=True, slots=True)
class Account:
    """
    Someone signing in at the fake Google.

    :param email: Their address.
    :type email: str
    :param verified: Whether Google has verified the address.
    :type verified: bool
    :param name: Their name.
    :type name: str
    """

    email: str
    verified: bool = True
    name: str = "Ada Lovelace"


@dataclass(frozen=True, slots=True)
class Grant:
    """
    What a sign-in code stands for.

    :param claims: The ID token to give for it.
    :type claims: dict[str, Any]
    :param challenge: The PKCE challenge its redeemer must answer.
    :type challenge: str
    """

    claims: dict[str, Any]
    challenge: str


class FakeGoogle:
    """
    Answers like Google, for one test. A test may change the key ID
    tokens are signed with (``signing_key``), the app they are for
    (``audience``), or stop it checking PKCE (``checks_pkce``), as a
    careless provider might not.
    """

    def __init__(self) -> None:
        """
        Make the keys, and no codes yet.
        """
        self.published_key = new_key()
        self.signing_key = self.published_key
        self.audience = CLIENT_ID
        self.checks_pkce = True
        self.grants: dict[str, Grant] = {}

    def transport(self) -> httpx.MockTransport:
        """
        Where to send AtomField's calls to Google.

        :return: A transport answered by this fake.
        :rtype: httpx.MockTransport
        """
        return httpx.MockTransport(self.answer)

    def answer(self, request: httpx.Request) -> httpx.Response:
        """
        Answer one call to Google.

        :param request: The call.
        :type request: httpx.Request
        :return: Google's answer.
        :rtype: httpx.Response
        """
        pages = {
            DISCOVERY_PATH: self.discovery,
            KEYS_PATH: self.keys,
            TOKEN_PATH: self.token,
        }
        return pages[request.url.path](request)

    def discovery(self, request: httpx.Request) -> httpx.Response:
        """
        Google's discovery document.

        :param request: The call.
        :type request: httpx.Request
        :return: Where Google's pages are.
        :rtype: httpx.Response
        """
        document = {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}{AUTHORIZATION_PATH}",
            "token_endpoint": f"{ISSUER}{TOKEN_PATH}",
            "jwks_uri": f"{ISSUER}{KEYS_PATH}",
        }
        return httpx.Response(httpx.codes.OK, json=document)

    def keys(self, request: httpx.Request) -> httpx.Response:
        """
        Google's published public key.

        :param request: The call.
        :type request: httpx.Request
        :return: A JWK set of one key.
        :rtype: httpx.Response
        """
        public = self.published_key.public_key()
        key = jwt.algorithms.RSAAlgorithm.to_jwk(public, as_dict=True)
        key.update(kid=KEY_ID, alg=ALGORITHM, use="sig")
        return httpx.Response(httpx.codes.OK, json={"keys": [key]})

    def token(self, request: httpx.Request) -> httpx.Response:
        """
        Redeem a sign-in code for an ID token, once.

        :param request: The call, a form.
        :type request: httpx.Request
        :return: The ID token, or Google's refusal.
        :rtype: httpx.Response
        """
        form = dict(parse_qsl(request.content.decode()))
        grant = self.grants.pop(form["code"], None)
        if grant is None or not self.redeemable(grant, form):
            return httpx.Response(
                httpx.codes.BAD_REQUEST, json={"error": "invalid_grant"}
            )
        signed = jwt.encode(
            grant.claims,
            self.signing_key,
            algorithm=ALGORITHM,
            headers={"kid": KEY_ID},
        )
        return httpx.Response(httpx.codes.OK, json={"id_token": signed})

    def redeemable(self, grant: Grant, form: dict[str, str]) -> bool:
        """
        Whether AtomField is redeeming, and answering the challenge
        (if this fake checks it).

        :param grant: What the code stands for.
        :type grant: Grant
        :param form: The redeeming call.
        :type form: dict[str, str]
        :return: True if Google would give the token.
        :rtype: bool
        """
        proof = pkce_challenge(form["code_verifier"])
        answered = proof == grant.challenge or not self.checks_pkce
        return form["client_secret"] == CLIENT_SECRET and answered

    def claims(self, account: Account, nonce: str) -> dict[str, Any]:
        """
        What an ID token for this account says.

        :param account: Who signed in.
        :type account: Account
        :param nonce: The sign-in's nonce, as AtomField sent it.
        :type nonce: str
        :return: The claims.
        :rtype: dict[str, Any]
        """
        now = int(time.time())
        return {
            "iss": ISSUER,
            "aud": self.audience,
            "sub": uuid.uuid5(uuid.NAMESPACE_DNS, account.email).hex,
            "iat": now,
            "exp": now + TOKEN_SECONDS,
            "nonce": nonce,
            "email": account.email,
            "email_verified": account.verified,
            "name": account.name,
        }

    def consent(self, login_link: str, account: Account) -> dict[str, str]:
        """
        Sign in on the fake Google's page.

        :param login_link: Where AtomField sent the browser.
        :type login_link: str
        :param account: Who signs in.
        :type account: Account
        :return: What Google sends the browser back with.
        :rtype: dict[str, str]
        """
        asked = query_of(login_link)
        assert asked["redirect_uri"] == REDIRECT_URI
        code = uuid.uuid4().hex
        claims = self.claims(account, asked["nonce"])
        self.grants[code] = Grant(claims, asked["code_challenge"])
        return {"code": code, "state": asked["state"]}

    def decline(self, login_link: str) -> dict[str, str]:
        """
        Say no on the fake Google's page.

        :param login_link: Where AtomField sent the browser.
        :type login_link: str
        :return: What Google sends the browser back with.
        :rtype: dict[str, str]
        """
        return {
            "error": "access_denied",
            "state": query_of(login_link)["state"],
        }
