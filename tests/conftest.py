"""
Shared fixtures: the API running in-process on throwaway test stores.

``pyproject.toml`` (pytest-env) points ``POSTGRES_DB`` and ``REDIS_DB``
at test-only stores before this module imports ``app``. Each test
session starts from an empty database and an empty Redis database.
"""

import asyncio
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.migrate import migrate
from app.main import app
from tests.stores import reset_test_stores

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
