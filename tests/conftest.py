"""
Shared fixtures: the API running in-process on throwaway test stores.

``pyproject.toml`` (pytest-env) points ``POSTGRES_DB`` and ``REDIS_DB``
at test-only stores before this module imports ``app``. Each test
session starts from an empty database and an empty Redis database.
"""

import asyncio
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, pool, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_sign_in
from app.core.config import settings
from app.db.migrate import migrate
from app.main import app, create_sign_in
from app.models.compute_target import HOUSE_TARGET_ID
from app.models.data_pack import DataPack
from app.models.run import Run
from app.models.script_release import ScriptRelease
from tests.browser import SIGN_IN_SETTINGS
from tests.fake_google import FakeGoogle
from tests.stores import make_redis, reset_test_stores

UserHeadersFactory = Callable[..., dict[str, str]]


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """
    Run the API in-process against freshly reset test stores.

    The schema is built by the same migration command production runs,
    then entering ``TestClient`` runs the app's lifespan (admin key,
    Redis pool), the same steps as a real server start.

    :return: One client, and one event loop, for the whole session.
    :rtype: Iterator[TestClient]
    """
    asyncio.run(reset_test_stores())
    migrate()
    with TestClient(app) as api_client:
        yield api_client


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    """
    Provide request headers carrying the administrator key.

    :return: Headers for administrator requests.
    :rtype: dict[str, str]
    """
    return {"X-API-Key": settings.ADMIN_API_KEY}


@pytest.fixture
def make_user_headers(client: TestClient) -> UserHeadersFactory:
    """
    Provide a factory that registers a new user and returns its headers.

    :param client: In-process API client.
    :type client: TestClient
    :return: Callable taking an optional label, returning headers.
    :rtype: UserHeadersFactory
    """

    def create_user_headers(label: str = "pytest_user") -> dict[str, str]:
        """
        Register a user key through the public API.

        :param label: Human-readable label stored with the key.
        :type label: str
        :return: Headers carrying the new key.
        :rtype: dict[str, str]
        """
        response = client.post("/api/auth/keys", json={"label": label})
        assert response.status_code == 201
        return {"X-API-Key": response.json()["api_key"]}

    return create_user_headers


@pytest.fixture
def make_session(client: TestClient) -> Iterator[async_sessionmaker]:
    """
    Sessions on a private engine for tests that use the database
    directly. NullPool opens a fresh connection per session, so each
    ``asyncio.run`` loop owns its connections (the app's pooled engine
    belongs to the TestClient's loop).

    :param client: In-process API client; its fixture migrated the DB.
    :type client: TestClient
    :return: Session factory.
    :rtype: Iterator[async_sessionmaker]
    """
    engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)


async def empty_house_queue() -> None:
    """
    Drop whatever waits in the house agent's queue.
    """
    redis = make_redis()
    try:
        await redis.delete(f"queue:{HOUSE_TARGET_ID}")
    finally:
        await redis.aclose()


async def forget_publications(make_session: async_sessionmaker) -> None:
    """
    Remove every release and data pack, unpinning the runs that used
    them.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    """
    async with make_session() as session:
        await session.execute(update(Run).values(release_id=None))
        await session.execute(delete(ScriptRelease))
        await session.execute(delete(DataPack))
        await session.commit()


@pytest.fixture
def releases(client: TestClient, make_session: async_sessionmaker) -> Iterator:
    """
    Start with an empty house queue; afterwards remove every release
    and data pack, so the tests after this one submit runs without a
    release, as before.

    :param client: In-process API client.
    :type client: TestClient
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :return: Nothing; cleans up afterwards.
    :rtype: Iterator
    """
    asyncio.run(empty_house_queue())
    yield
    asyncio.run(forget_publications(make_session))


@pytest.fixture
def google(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeGoogle]:
    """
    Sign-in set up as the settings say, against a fake Google; the
    browser (the test client) forgets its cookies afterwards.

    :param client: In-process API client.
    :type client: TestClient
    :param monkeypatch: Sets the sign-in settings for this test.
    :type monkeypatch: pytest.MonkeyPatch
    :return: The fake Google.
    :rtype: Iterator[FakeGoogle]
    """
    fake = FakeGoogle()
    for name, value in SIGN_IN_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    http = httpx.AsyncClient(transport=fake.transport())
    flow = create_sign_in(http, app.state.redis)
    app.dependency_overrides[get_sign_in] = lambda: flow
    yield fake
    del app.dependency_overrides[get_sign_in]
    client.cookies.clear()
