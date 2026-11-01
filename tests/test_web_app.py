"""
The server serves the built web app itself, so one address is enough:
the pages, the API and the sign-in callback all live on it.
"""

from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web_app import WEB_APP_NAME

HOME_PAGE = "<title>the built web app</title>"
SCRIPT = "console.log(1);"
SECRET = "a file beside the built folder"


def built_web_app() -> object:
    """
    The web app's mount in the real application.

    :return: The ASGI app that serves the built files.
    :rtype: object
    """
    return next(
        route.app
        for route in app.routes
        if getattr(route, "name", None) == WEB_APP_NAME
    )


@pytest.fixture
def pages(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """
    The API with a small built web app in a temporary folder, and a file
    beside that folder that must never be served.

    :param client: The API in-process.
    :type client: TestClient
    :param tmp_path: A temporary folder.
    :type tmp_path: Path
    :param monkeypatch: Points the mount at the folder for this test.
    :type monkeypatch: pytest.MonkeyPatch
    :yield: The same client.
    :rtype: Iterator[TestClient]
    """
    built = tmp_path / "dist"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text(HOME_PAGE)
    (built / "assets" / "app.js").write_text(SCRIPT)
    (tmp_path / "secret.env").write_text(SECRET)
    monkeypatch.setattr(built_web_app(), "all_directories", [str(built)])
    yield client


def test_the_home_page_is_the_web_app(pages: TestClient) -> None:
    """
    The address people open shows the pages.

    :param pages: The API with a built web app.
    :type pages: TestClient
    """
    reply = pages.get("/")

    assert reply.status_code == HTTPStatus.OK
    assert HOME_PAGE in reply.text
    assert reply.headers["content-type"].startswith("text/html")


def test_the_pages_own_files_are_served(pages: TestClient) -> None:
    """
    The scripts the pages load come from the same address.

    :param pages: The API with a built web app.
    :type pages: TestClient
    """
    reply = pages.get("/assets/app.js")

    assert reply.status_code == HTTPStatus.OK
    assert reply.text == SCRIPT
    assert "javascript" in reply.headers["content-type"]


def test_the_api_comes_before_the_pages(pages: TestClient) -> None:
    """
    A route still answers as itself, and an unknown API path is a plain
    404 rather than a page, so a script never mistakes one for a reply.

    :param pages: The API with a built web app.
    :type pages: TestClient
    """
    health = pages.get("/health")
    unknown = pages.get("/api/no-such-route")

    assert health.json()["status"]
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert HOME_PAGE not in unknown.text
    assert unknown.json() == {"detail": "Not Found"}


def test_a_scripts_mistakes_are_named_correctly(pages: TestClient) -> None:
    """
    The web app takes no part in the API: a wrong address is not found
    and a wrong method not allowed, whichever method is used.

    :param pages: The API with a built web app.
    :type pages: TestClient
    """
    wrong_address = pages.post("/api/no-such-route")
    wrong_method = pages.post("/api/task-definitions")
    write_to_a_page = pages.post("/")

    assert wrong_address.status_code == HTTPStatus.NOT_FOUND
    assert wrong_method.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert write_to_a_page.status_code == HTTPStatus.METHOD_NOT_ALLOWED


@pytest.mark.parametrize(
    "path",
    ["/../secret.env", "/%2e%2e/secret.env", "/..%2fsecret.env"],
)
def test_nothing_outside_the_built_folder_is_served(
    pages: TestClient,
    path: str,
) -> None:
    """
    However the path is written, it cannot climb out of the folder.

    :param pages: The API with a built web app.
    :type pages: TestClient
    :param path: A path trying to leave the folder.
    :type path: str
    """
    reply = pages.get(path)

    assert SECRET not in reply.text
    assert reply.status_code == HTTPStatus.NOT_FOUND


def test_without_a_built_web_app_the_home_page_is_not_found(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A server with no build still starts and serves its API.

    :param client: The API in-process.
    :type client: TestClient
    :param tmp_path: A temporary folder.
    :type tmp_path: Path
    :param monkeypatch: Points the mount at a missing folder.
    :type monkeypatch: pytest.MonkeyPatch
    """
    missing = str(tmp_path / "not-built")
    monkeypatch.setattr(built_web_app(), "all_directories", [missing])

    assert client.get("/").status_code == HTTPStatus.NOT_FOUND
    assert client.get("/health").status_code == HTTPStatus.OK
