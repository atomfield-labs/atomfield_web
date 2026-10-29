"""
Cryptographic security and API key token generation utilities.
"""

import hashlib
import secrets

# The request header that carries a user's or the administrator's key.
API_KEY_HEADER = "X-API-Key"
# How much of a key is shown to tell keys apart: never enough to use.
SHOWN_KEY_CHARACTERS = 12
# The cookie that tells a signed-in browser's requests apart.
SESSION_COOKIE = "atomfield_session"
# Prefixes say what a secret is if one turns up in a log or a paste.
AGENT_TOKEN_PREFIX = "af_agent_"
SESSION_TOKEN_PREFIX = "af_session_"
TOKEN_BYTES = 32


def hash_api_key(raw_key: str) -> str:
    """
    Compute deterministic SHA-256 hex digest for storage and verification.

    :param raw_key: Plaintext API key token provided by the client.
    :type raw_key: str
    :return: 64-character hexadecimal SHA-256 hash.
    :rtype: str
    """
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def display_prefix(secret: str) -> str:
    """
    The start of a key, shown to tell keys apart.

    :param secret: The key.
    :type secret: str
    :return: e.g. ``af_live_Xy3k...``.
    :rtype: str
    """
    return f"{secret[:SHOWN_KEY_CHARACTERS]}..."


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate cryptographically random API key, public prefix, and hash.

    :return: Tuple of (raw_secret_key, display_prefix, sha256_hash).
    :rtype: tuple[str, str, str]
    """
    token_entropy = secrets.token_urlsafe(24)
    raw_key = f"af_live_{token_entropy}"
    return raw_key, display_prefix(raw_key), hash_api_key(raw_key)


def generate_token(prefix: str) -> tuple[str, str]:
    """
    Generate a secret that proves who holds it, and the hash that is
    stored in its place.

    :param prefix: What kind of secret it is, e.g. ``af_agent_``.
    :type prefix: str
    :return: (the secret, its SHA-256 hash).
    :rtype: tuple[str, str]
    """
    token = f"{prefix}{secrets.token_urlsafe(TOKEN_BYTES)}"
    return token, hash_api_key(token)


def generate_agent_token() -> tuple[str, str]:
    """
    Generate an agent's bearer token and the hash that is stored.

    :return: (token shown once to the user, its SHA-256 hash).
    :rtype: tuple[str, str]
    """
    return generate_token(AGENT_TOKEN_PREFIX)


def generate_session_token() -> tuple[str, str]:
    """
    Generate the secret a signed-in browser keeps in its cookie, and
    the hash that is stored.

    :return: (the secret for the cookie, its SHA-256 hash).
    :rtype: tuple[str, str]
    """
    return generate_token(SESSION_TOKEN_PREFIX)
