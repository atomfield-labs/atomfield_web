"""
People and their API keys: making a person, and a key for their
scripts (the key itself is shown once and stored only as a hash).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.user import User


async def add_person(db: AsyncSession, name: str | None) -> User:
    """
    Add a new person, flushed so they have an id.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param name: How they are shown, if known.
    :type name: str | None
    :return: The person.
    :rtype: User
    """
    user = User(name=name)
    db.add(user)
    await db.flush()
    return user


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
