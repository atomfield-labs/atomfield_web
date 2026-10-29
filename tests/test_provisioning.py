"""
Startup provisioning is safe when several API processes start at once,
and the administrator is a person who owns the admin key.
"""

import asyncio
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.security import hash_api_key
from app.main import provision_admin
from app.models.api_key import ApiKey
from app.models.user import User

UserHeadersFactory = Callable[..., dict[str, str]]


async def provision(make_session: async_sessionmaker) -> None:
    """
    One API process starting.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    async with make_session() as session:
        await provision_admin(session)


async def owners_of_key(
    make_session: async_sessionmaker, key_hash: str
) -> list[bool]:
    """
    Whether the person owning each key with this fingerprint is admin.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param key_hash: The key's fingerprint.
    :type key_hash: str
    :return: One flag per key.
    :rtype: list[bool]
    """
    async with make_session() as session:
        query = (
            select(User.is_admin)
            .join(ApiKey, ApiKey.user_id == User.id)
            .where(ApiKey.key_hash == key_hash)
        )
        return list((await session.execute(query)).scalars())


async def change_owner(
    make_session: async_sessionmaker, key_hash: str, remove: bool
) -> None:
    """
    Clean up after a test: remove the key's owner (and so the key), or
    make them an ordinary person again.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param key_hash: The key's fingerprint.
    :type key_hash: str
    :param remove: Remove the owner rather than demote them.
    :type remove: bool
    """
    owner = select(ApiKey.user_id).where(ApiKey.key_hash == key_hash)
    is_owner = User.id == owner.scalar_subquery()
    statement = (
        delete(User).where(is_owner)
        if remove
        else update(User).where(is_owner).values(is_admin=False)
    )
    async with make_session() as session:
        await session.execute(statement)
        await session.commit()


async def provision_and_look(
    make_session: async_sessionmaker, key_hash: str, processes: int
) -> list[bool]:
    """
    Start API processes at the same moment, then look at the key.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param key_hash: Fingerprint of the admin key.
    :type key_hash: str
    :param processes: How many start together.
    :type processes: int
    :return: Admin flag of each key's owner.
    :rtype: list[bool]
    """
    starts = (provision(make_session) for _ in range(processes))
    await asyncio.gather(*starts)
    return await owners_of_key(make_session, key_hash)


def test_processes_starting_together_create_one_administrator(
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Two processes provision the administrator at the same moment:
    neither fails, and exactly one key exists, owned by an admin.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param monkeypatch: Sets a fresh admin key for this test.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(
        settings, "ADMIN_API_KEY", f"af_admin_race_{uuid.uuid4().hex}"
    )
    key_hash = hash_api_key(settings.ADMIN_API_KEY)
    owners = asyncio.run(provision_and_look(make_session, key_hash, 2))
    asyncio.run(change_owner(make_session, key_hash, remove=True))
    assert owners == [True]


def test_an_existing_admin_key_makes_its_owner_the_administrator(
    make_session: async_sessionmaker,
    make_user_headers: UserHeadersFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A key that already exists (as after the upgrade that turned every
    key into a person) keeps its person, who becomes the admin; no
    second person is made.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param monkeypatch: Makes that key the admin key.
    :type monkeypatch: pytest.MonkeyPatch
    """
    secret = make_user_headers()["X-API-Key"]
    monkeypatch.setattr(settings, "ADMIN_API_KEY", secret)
    key_hash = hash_api_key(secret)
    owners = asyncio.run(provision_and_look(make_session, key_hash, 1))
    asyncio.run(change_owner(make_session, key_hash, remove=False))
    assert owners == [True]
