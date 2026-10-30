"""
People and how they prove who they are: API keys for their scripts,
and sessions for the browsers they sign in on. Keys and session
secrets are shown once and stored only as hashes.
"""

import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    generate_api_key,
    generate_session_token,
    hash_api_key,
)
from app.models.api_key import ApiKey
from app.models.browser_session import BrowserSession
from app.models.user import NAME_LENGTH, User
from app.sign_in.provider import Identity


def new_key(user_id: uuid.UUID, label: str | None) -> tuple[str, ApiKey]:
    """
    A new API key for a person's scripts.

    :param user_id: The person.
    :type user_id: uuid.UUID
    :param label: What the key is for.
    :type label: str | None
    :return: The secret (to show once) and the row to store.
    :rtype: tuple[str, ApiKey]
    """
    secret, prefix, key_hash = generate_api_key()
    key = ApiKey(
        user_id=user_id, key_hash=key_hash, key_prefix=prefix, label=label
    )
    return secret, key


async def keys_of(db: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
    """
    A person's keys that still work, newest first.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    :return: Their working keys.
    :rtype: list[ApiKey]
    """
    query = (
        select(ApiKey)
        .where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
        .order_by(ApiKey.created_at.desc())
    )
    return list((await db.scalars(query)).all())


async def revoke_key(
    db: AsyncSession, user_id: uuid.UUID, key_id: uuid.UUID
) -> bool:
    """
    Stop one of a person's keys working. One conditional UPDATE: it
    can only touch a working key of theirs.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    :param key_id: The key.
    :type key_id: uuid.UUID
    :return: True if a key was revoked.
    :rtype: bool
    """
    theirs = (
        ApiKey.id == key_id,
        ApiKey.user_id == user_id,
        ApiKey.is_active.is_(True),
    )
    revoke = update(ApiKey).where(*theirs).values(is_active=False)
    result = await db.execute(revoke)
    await db.commit()
    return result.rowcount == 1


async def person_signing_in(
    db: AsyncSession, identity: Identity, is_admin: bool
) -> User:
    """
    The person with this email, made on their first sign-in. Their
    name, and whether they are an administrator, follow each sign-in.
    One statement (an upsert), so two first sign-ins at once still
    make one person.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param identity: Who the provider says signed in.
    :type identity: Identity
    :param is_admin: Whether the rules make them an administrator.
    :type is_admin: bool
    :return: The person.
    :rtype: User
    """
    name = identity.name[:NAME_LENGTH] if identity.name else None
    changes = {"name": name, "is_admin": is_admin, "last_seen_at": func.now()}
    upsert = (
        insert(User)
        .values(email=identity.email, **changes)
        .on_conflict_do_update(index_elements=[User.email], set_=changes)
        .returning(User)
    )
    fresh = {"populate_existing": True}
    return (await db.scalars(upsert, execution_options=fresh)).one()


async def sign_in_browser(
    db: AsyncSession, user_id: uuid.UUID, lifetime: timedelta
) -> str:
    """
    Sign a person in on one browser, committing along with whatever
    the caller has done. Their sessions that have ended are cleared
    away.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    :param lifetime: How long the session lasts.
    :type lifetime: timedelta
    :return: The secret for the browser's cookie.
    :rtype: str
    """
    token, token_hash = generate_session_token()
    ended = delete(BrowserSession).where(
        BrowserSession.user_id == user_id,
        BrowserSession.expires_at <= func.now(),
    )
    await db.execute(ended)
    expires_at = func.now() + lifetime
    db.add(
        BrowserSession(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
    )
    await db.commit()
    return token


async def sign_out_browser(db: AsyncSession, token: str) -> None:
    """
    End a browser's session now.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param token: The secret from the browser's cookie.
    :type token: str
    """
    token_hash = hash_api_key(token)
    ended = delete(BrowserSession).where(
        BrowserSession.token_hash == token_hash
    )
    await db.execute(ended)
    await db.commit()
