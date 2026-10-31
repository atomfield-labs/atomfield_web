"""
Publish a release of the scripts::

    python -m app.releases.publish                  # scripts_repo, HEAD
    python -m app.releases.publish --repo ~/afscripts --ref main

It builds exactly one git commit, never the working folder, so files
you are still editing (committed or not) never ship by accident:

1. copy the commit out of git into a temporary folder;
2. add the commit to the version (``0.1.0`` becomes ``0.1.0+g2e6d386``):
   every commit is its own release, with no version to bump by hand,
   and the version says where it came from;
3. stop there if the server already has that version;
4. compile each package for each kind of computer (``compiling``), so
   no readable code leaves this computer;
5. upload one bundle, the catalog and the compiled packages, with the
   administrator key (``ADMIN_API_KEY``).

Publishing the same commit again changes nothing: the server keeps the
release it already has.
"""

import argparse
import tempfile
import zipfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from app.core.cli import fail, print_outcome, stops_cleanly
from app.core.config import settings
from app.core.names import version_label
from app.core.security import API_KEY_HEADER
from app.releases.compiling import (
    MACHINES,
    build_bundle,
    labelled_version,
    project_name,
)
from app.releases.published import PublishConflictError
from app.releases.tools import PublishError, run_tool

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = REPO_ROOT / "scripts_repo"
DEFAULT_API_URL = "http://localhost:8000"
RELEASES_PATH = "/api/releases"
UPLOAD_SECONDS = 120.0
ALREADY_PUBLISHED = "{label} was already published; nothing changed."
NOT_FOUND = httpx.codes.NOT_FOUND
# Answers that took a request: already there (or a listing), or new.
ACCEPTED = (httpx.codes.OK, httpx.codes.CREATED)


# What publishing can fail with, each saying why in its message.
PUBLISH_ERRORS = (PublishError, PublishConflictError)


def resolve_commit(repo: Path, ref: str) -> str:
    """
    The full commit a branch, tag or commit name points to.

    :param repo: The scripts repository.
    :type repo: Path
    :param ref: Branch, tag or commit.
    :type ref: str
    :return: 40-character commit id.
    :rtype: str
    """
    git = ["git", "-C", str(repo), "rev-parse", "--verify"]
    return run_tool([*git, f"{ref}^{{commit}}"]).strip()


def export_commit(repo: Path, commit: str, tree: Path) -> None:
    """
    Copy one commit's files (and nothing else) into ``tree``.

    :param repo: The scripts repository.
    :type repo: Path
    :param commit: The commit.
    :type commit: str
    :param tree: Empty folder to fill.
    :type tree: Path
    """
    archive = tree.with_name(f"{tree.name}.zip")
    git = ["git", "-C", str(repo), "archive", "--format=zip"]
    run_tool([*git, f"--output={archive}", commit])
    with zipfile.ZipFile(archive) as source:
        source.extractall(tree)


def call_api(
    send: Callable[..., httpx.Response],
    api_url: str,
    path: str,
    **options: Any,
) -> httpx.Response:
    """
    Send one request to the API. Not reaching it is a PublishError
    naming it, not a connection traceback.

    :param send: ``httpx.get`` or ``httpx.post``.
    :type send: Callable[..., httpx.Response]
    :param api_url: The API's address.
    :type api_url: str
    :param path: The route, e.g. ``/api/releases``.
    :type path: str
    :param options: For ``send``: body, headers, timeout...
    :type options: Any
    :return: The response.
    :rtype: httpx.Response
    :raises PublishError: If the API cannot be reached.
    """
    try:
        return send(f"{api_url.rstrip('/')}{path}", **options)
    except httpx.HTTPError as error:
        raise PublishError(f"Could not reach {api_url}: {error}") from error


def admin_headers(admin_key: str) -> dict[str, str]:
    """
    Headers that carry the administrator's key.

    :param admin_key: The key.
    :type admin_key: str
    :return: The headers.
    :rtype: dict[str, str]
    """
    return {API_KEY_HEADER: admin_key}


def accepted(response: httpx.Response) -> Any:
    """
    The body of an answer that took the request (``ACCEPTED``).

    :param response: The API's answer.
    :type response: httpx.Response
    :return: Its JSON body.
    :rtype: Any
    :raises PublishError: If the API refused it, with its reason.
    """
    if response.status_code not in ACCEPTED:
        raise PublishError(f"The API refused it: {response.text}")
    return response.json()


def on_server(api_url: str, name: str, version: str) -> bool:
    """
    Whether the server already has this release, so the build can be
    skipped: building takes minutes.

    :param api_url: The API's address.
    :type api_url: str
    :param name: The release's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :return: True if it was published.
    :rtype: bool
    :raises PublishError: If the API cannot be reached or refuses.
    """
    response = call_api(
        httpx.get,
        api_url,
        f"{RELEASES_PATH}/{name}/{version}",
        timeout=UPLOAD_SECONDS,
    )
    if response.status_code == NOT_FOUND:
        return False
    accepted(response)
    return True


def upload(api_url: str, admin_key: str, bundle: bytes, commit: str) -> str:
    """
    Publish the bundle and describe what the server did.

    :param api_url: The API's address.
    :type api_url: str
    :param admin_key: The administrator's key.
    :type admin_key: str
    :param bundle: The bundle.
    :type bundle: bytes
    :param commit: The commit it was built from.
    :type commit: str
    :return: One line for the person publishing.
    :rtype: str
    :raises PublishError: If the server refused it or was not there.
    """
    response = call_api(
        httpx.post,
        api_url,
        RELEASES_PATH,
        params={"git_commit": commit},
        content=bundle,
        headers=admin_headers(admin_key),
        timeout=UPLOAD_SECONDS,
    )
    release = accepted(response)
    label = version_label(release["name"], release["version"])
    if response.status_code == httpx.codes.OK:
        return ALREADY_PUBLISHED.format(label=label)
    return f"Published {label} (sha256 {release['sha256'][:12]})."


def publish(
    repo: Path,
    ref: str,
    api_url: str,
    admin_key: str,
    machines: tuple[str, ...] = MACHINES,
) -> str:
    """
    Build one commit of the scripts and publish it.

    :param repo: The scripts repository.
    :type repo: Path
    :param ref: Branch, tag or commit to publish.
    :type ref: str
    :param api_url: The API's address.
    :type api_url: str
    :param admin_key: The administrator's key.
    :type admin_key: str
    :param machines: The kinds of computer to build for.
    :type machines: tuple[str, ...]
    :return: What happened.
    :rtype: str
    """
    commit = resolve_commit(repo, ref)
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch) / "source"
        export_commit(repo, commit, tree)
        name, version = project_name(tree), labelled_version(tree, commit)
        if on_server(api_url, name, version):
            return ALREADY_PUBLISHED.format(label=version_label(name, version))
        build = Path(scratch) / "build"
        bundle = build_bundle(tree, version, build, machines)
        return upload(api_url, admin_key, bundle, commit)


def run_with_admin_key(publishing: Callable[[str], str]) -> int:
    """
    Publish with the administrator's key (``ADMIN_API_KEY``), and print
    what happened.

    :param publishing: Publishes with the key it is given; returns
        what happened.
    :type publishing: Callable[[str], str]
    :return: The command's exit code.
    :rtype: int
    """
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        return fail("set ADMIN_API_KEY")
    return print_outcome(partial(publishing, admin_key), PUBLISH_ERRORS)


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line.

    :return: Parser for ``python -m app.releases.publish``.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.releases.publish",
        description="Publish one commit of the scripts as a release.",
    )
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--ref", default="HEAD", help="Branch, tag or commit")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--machines",
        nargs="+",
        choices=MACHINES,
        default=MACHINES,
        help="Kinds of computer to build for (default: all)",
    )
    return parser


@stops_cleanly(
    "Stopped. Publishing again is safe: a published commit changes nothing."
)
def main(argv: list[str] | None = None) -> int:
    """
    Command line: publish, and print what happened.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    publishing = partial(
        publish,
        options.repo,
        options.ref,
        options.api_url,
        machines=tuple(options.machines),
    )
    return run_with_admin_key(publishing)


if __name__ == "__main__":
    raise SystemExit(main())
