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
from app.main import provision_admin, provision_owners, starting_catalog
from app.models.api_key import ApiKey
from app.models.user import Role, User

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
    Whether the person holding each key with this fingerprint is an
    owner.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param key_hash: The key's fingerprint.
    :type key_hash: str
    :return: One flag per key.
    :rtype: list[bool]
    """
    async with make_session() as session:
        query = (
            select(User.role == Role.OWNER)
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
        else update(User).where(is_owner).values(role=Role.USER)
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


async def add_person(
    make_session: async_sessionmaker, email: str, role: Role
) -> None:
    """
    Make a person.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param email: Their email.
    :type email: str
    :param role: Their role.
    :type role: Role
    """
    async with make_session() as session:
        session.add(User(email=email, role=role))
        await session.commit()


async def role_of(make_session: async_sessionmaker, email: str) -> str:
    """
    A person's role.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param email: Their email.
    :type email: str
    :return: Their role.
    :rtype: str
    """
    query = select(User.role).where(User.email == email)
    async with make_session() as session:
        return await session.scalar(query)


async def start_with_owners(make_session: async_sessionmaker) -> None:
    """
    What a server start does about the list of owners.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    async with make_session() as session:
        await provision_owners(session)


def test_the_list_of_owners_counts_from_the_next_start(
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    A start makes those on the list owners and those off it users, so
    nobody keeps or waits for ownership until their next sign-in.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param monkeypatch: Sets the list of owners.
    :type monkeypatch: pytest.MonkeyPatch
    """
    tag = uuid.uuid4().hex
    joining, leaving = f"joining{tag}@lab.ac.in", f"leaving{tag}@lab.ac.in"
    asyncio.run(add_person(make_session, joining, Role.USER))
    asyncio.run(add_person(make_session, leaving, Role.OWNER))
    monkeypatch.setattr(settings, "OWNER_EMAILS", joining)
    asyncio.run(start_with_owners(make_session))
    assert asyncio.run(role_of(make_session, joining)) == Role.OWNER
    assert asyncio.run(role_of(make_session, leaving)) == Role.USER


def test_a_server_needs_no_scripts_to_start(monkeypatch: pytest.MonkeyPatch):
    """
    A server holds no scripts: with no catalog file it starts with no
    tasks, until the first release.

    :param monkeypatch: Clears the catalog setting.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(settings, "CATALOG_PATH", None)
    assert not starting_catalog().tasks
