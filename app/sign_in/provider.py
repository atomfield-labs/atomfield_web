"""
Talking to the OpenID Connect provider (Google): where to send people
to sign in, and checking the ID token it hands back for them.

Nothing is cached. People sign in rarely, and asking afresh each time
means a moved endpoint or a rotated signing key never needs a restart.
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.sign_in.refusals import SignInProblem, SignInRefused

logger = logging.getLogger(__name__)

DISCOVERY_PATH = "/.well-known/openid-configuration"
# What AtomField asks to learn: who you are, your email and your name.
SCOPES = "openid email profile"
CODE_RESPONSE = "code"
CODE_GRANT = "authorization_code"
CHALLENGE_METHOD = "S256"
SIGNING_ALGORITHMS = ("RS256",)
# Claims an ID token must carry to be used at all.
REQUIRED_CLAIMS = ("iss", "aud", "exp", "iat", "nonce", "email")
# How far apart the provider's clock and this server's may be.
CLOCK_LEEWAY_SECONDS = 60
SECRET_BYTES = 32
HTTPS_PREFIX = "https://"
CODE_REFUSED = "The provider refused a sign-in code (%s): %s"
TOKEN_REFUSED = "An ID token was refused: %s"


@dataclass(frozen=True, slots=True)
class Registration:
    """
    AtomField as registered with the provider.

    :param issuer: The provider, e.g. ``https://accounts.google.com``.
    :type issuer: str
    :param client_id: AtomField's id there.
    :type client_id: str
    :param client_secret: AtomField's secret there.
    :type client_secret: str
    :param redirect_uri: Where the provider sends people back.
    :type redirect_uri: str
    """

    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def issuers(self) -> tuple[str, str]:
        """
        The provider's name as its tokens may write it: Google's come
        with or without ``https://``.

        :return: Both spellings.
        :rtype: tuple[str, str]
        """
        return self.issuer, self.issuer.removeprefix(HTTPS_PREFIX)


@dataclass(frozen=True, slots=True)
class Endpoints:
    """
    The provider's addresses, from its discovery document.

    :param authorization: Where people sign in.
    :type authorization: str
    :param token: Where a sign-in code is redeemed for an ID token.
    :type token: str
    :param keys: Where the keys that sign ID tokens are published.
    :type keys: str
    """

    authorization: str
    token: str
    keys: str


@dataclass(frozen=True, slots=True)
class SignInStart:
    """
    The secrets of one sign-in in progress.

    :param state: Ties the provider's answer to the browser that asked.
    :type state: str
    :param nonce: Ties the ID token to this sign-in, so a token from
        another one cannot be slipped in.
    :type nonce: str
    :param verifier: Proves (PKCE) that whoever redeems the code is
        whoever asked for it.
    :type verifier: str
    """

    state: str
    nonce: str
    verifier: str

    @classmethod
    def new(cls) -> "SignInStart":
        """
        Fresh, unguessable secrets for a new sign-in.

        :return: The sign-in's secrets.
        :rtype: SignInStart
        """
        return cls(
            state=secrets.token_urlsafe(SECRET_BYTES),
            nonce=secrets.token_urlsafe(SECRET_BYTES),
            verifier=secrets.token_urlsafe(SECRET_BYTES),
        )

    @property
    def challenge(self) -> str:
        """
        What the provider is shown at the start: the verifier's
        SHA-256, so the verifier itself is revealed only when the code
        is redeemed.

        :return: The PKCE challenge.
        :rtype: str
        """
        digest = hashlib.sha256(self.verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@dataclass(frozen=True, slots=True)
class Identity:
    """
    Who the provider says signed in.

    :param email: Their email, lower case, verified by the provider.
    :type email: str
    :param name: Their name, if they share it.
    :type name: str | None
    """

    email: str
    name: str | None

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "Identity":
        """
        Read who signed in from a checked ID token.

        :param claims: The token's contents.
        :type claims: dict[str, Any]
        :return: Who signed in.
        :rtype: Identity
        :raises SignInRefused: If the provider has not verified the
            email, since then nothing shows it is really theirs.
        """
        if claims.get("email_verified") is not True:
            raise SignInRefused(SignInProblem.FAILED)
        return cls(
            email=claims["email"].lower(),
            name=claims.get("name"),
        )


def signing_key(token: str, keys: dict[str, Any]) -> jwt.PyJWK:
    """
    The provider's key that signed a token, found by the key id in the
    token's header.

    :param token: The ID token.
    :type token: str
    :param keys: The provider's published keys (a JWK set).
    :type keys: dict[str, Any]
    :return: The key.
    :rtype: jwt.PyJWK
    :raises jwt.PyJWTError: If the provider has no such key.
    """
    key_id = jwt.get_unverified_header(token).get("kid")
    for key in jwt.PyJWKSet.from_dict(keys).keys:
        if key.key_id == key_id:
            return key
    raise jwt.InvalidKeyError(f"The provider has no key {key_id}")


class IdentityProvider:
    """
    One OpenID Connect provider, as AtomField is registered with it.
    """

    def __init__(
        self, http: httpx.AsyncClient, registration: Registration
    ) -> None:
        """
        Bind to the provider.

        :param http: Client for calling the provider.
        :type http: httpx.AsyncClient
        :param registration: AtomField's registration there.
        :type registration: Registration
        """
        self.http = http
        self.registration = registration

    async def fetch(self, url: str) -> dict[str, Any]:
        """
        One of the documents the provider publishes.

        :param url: Its address.
        :type url: str
        :return: The document.
        :rtype: dict[str, Any]
        :raises httpx.HTTPStatusError: If the provider cannot answer.
        """
        response = await self.http.get(url)
        response.raise_for_status()
        return response.json()

    async def endpoints(self) -> Endpoints:
        """
        Where the provider's sign-in page, token endpoint and keys are.

        :return: The addresses.
        :rtype: Endpoints
        """
        issuer = self.registration.issuer
        document = await self.fetch(f"{issuer}{DISCOVERY_PATH}")
        return Endpoints(
            authorization=document["authorization_endpoint"],
            token=document["token_endpoint"],
            keys=document["jwks_uri"],
        )

    async def login_link(self, start: SignInStart) -> str:
        """
        The provider's sign-in page for one sign-in.

        :param start: The sign-in's secrets.
        :type start: SignInStart
        :return: The link to send the browser to.
        :rtype: str
        """
        endpoints = await self.endpoints()
        query = {
            "response_type": CODE_RESPONSE,
            "client_id": self.registration.client_id,
            "redirect_uri": self.registration.redirect_uri,
            "scope": SCOPES,
            "state": start.state,
            "nonce": start.nonce,
            "code_challenge": start.challenge,
            "code_challenge_method": CHALLENGE_METHOD,
        }
        return f"{endpoints.authorization}?{urlencode(query)}"

    async def id_token(
        self, code: str, start: SignInStart, endpoints: Endpoints
    ) -> str:
        """
        Redeem the code the browser brought back for an ID token. The
        server asks, with its own secret and the PKCE verifier, so a
        code caught on its way through the browser is useless.

        :param code: The code from the provider's answer.
        :type code: str
        :param start: The sign-in's secrets.
        :type start: SignInStart
        :param endpoints: The provider's addresses.
        :type endpoints: Endpoints
        :return: The ID token, not yet checked.
        :rtype: str
        :raises SignInRefused: If the provider refuses the code.
        """
        form = {
            "grant_type": CODE_GRANT,
            "code": code,
            "redirect_uri": self.registration.redirect_uri,
            "client_id": self.registration.client_id,
            "client_secret": self.registration.client_secret,
            "code_verifier": start.verifier,
        }
        response = await self.http.post(endpoints.token, data=form)
        if response.is_error:
            logger.warning(CODE_REFUSED, response.status_code, response.text)
            raise SignInRefused(SignInProblem.FAILED)
        return response.json()["id_token"]

    def checked_claims(
        self, token: str, keys: dict[str, Any]
    ) -> dict[str, Any]:
        """
        An ID token's contents, once it has shown it was signed by the
        provider, for AtomField, and is still current.

        :param token: The ID token.
        :type token: str
        :param keys: The provider's published keys.
        :type keys: dict[str, Any]
        :return: The token's claims.
        :rtype: dict[str, Any]
        :raises SignInRefused: If any of that does not hold.
        """
        try:
            return jwt.decode(
                token,
                signing_key(token, keys),
                algorithms=SIGNING_ALGORITHMS,
                audience=self.registration.client_id,
                issuer=self.registration.issuers,
                leeway=CLOCK_LEEWAY_SECONDS,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as error:
            logger.warning(TOKEN_REFUSED, error)
            raise SignInRefused(SignInProblem.FAILED) from error

    async def identity(self, code: str, start: SignInStart) -> Identity:
        """
        Who signed in, from the provider's answer to one sign-in.

        :param code: The code from the provider's answer.
        :type code: str
        :param start: The sign-in's secrets.
        :type start: SignInStart
        :return: Who signed in.
        :rtype: Identity
        :raises SignInRefused: If the answer does not check out, or is
            for a different sign-in (its nonce).
        """
        endpoints = await self.endpoints()
        token = await self.id_token(code, start, endpoints)
        claims = self.checked_claims(token, await self.fetch(endpoints.keys))
        if claims["nonce"] != start.nonce:
            raise SignInRefused(SignInProblem.FAILED)
        return Identity.from_claims(claims)
