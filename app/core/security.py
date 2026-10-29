"""
Cryptographic security and API key token generation utilities.
"""

import hashlib
import secrets

# The request header that carries a user's or the administrator's key.
API_KEY_HEADER = "X-API-Key"


def hash_api_key(raw_key: str) -> str:
    """
    Compute deterministic SHA-256 hex digest for storage and verification.

    :param raw_key: Plaintext API key token provided by the client.
    :type raw_key: str
    :return: 64-character hexadecimal SHA-256 hash.
    :rtype: str
    """
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate cryptographically random API key, public prefix, and hash.

    :return: Tuple of (raw_secret_key, display_prefix, sha256_hash).
    :rtype: tuple[str, str, str]
    """
    token_entropy = secrets.token_urlsafe(24)
    raw_key = f"af_live_{token_entropy}"
    display_prefix = f"{raw_key[:12]}..."
    key_hash = hash_api_key(raw_key)
    return raw_key, display_prefix, key_hash


def generate_agent_token() -> tuple[str, str]:
    """
    Generate an agent's bearer token and the hash that is stored.

    :return: (token shown once to the user, its SHA-256 hash).
    :rtype: tuple[str, str]
    """
    token = f"af_agent_{secrets.token_urlsafe(32)}"
    return token, hash_api_key(token)
