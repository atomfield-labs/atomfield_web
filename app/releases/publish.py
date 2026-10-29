"""
Publish a release of the scripts::

    python -m app.releases.publish                  # scripts_repo, HEAD
    python -m app.releases.publish --repo ~/afscripts --ref main

It builds exactly one git commit, never the working folder, so files
you are still editing (committed or not) never ship by accident:

1. copy the commit out of git into a temporary folder;
2. put the commit's ``catalog.json`` inside the package, so the code
   and its catalog travel as one file;
3. add the commit to the version (``0.1.0`` becomes
   ``0.1.0+g2e6d386``): every commit is its own release, with no
   version to bump by hand, and the version says where it came from;
4. build the wheel with ``uv build``;
5. upload it with the administrator key (``ADMIN_API_KEY``).

Publishing the same commit again changes nothing: the build gives the
same bytes, and the server keeps the release it already has.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

import httpx

from app.core.cli import stops_cleanly
from app.core.config import settings
from app.releases.wheel import CATALOG_NAME, package_name

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = REPO_ROOT / "scripts_repo"
DEFAULT_API_URL = "http://localhost:8000"
UPLOAD_SECONDS = 120.0
SHORT_COMMIT = 7


class PublishError(RuntimeError):
    """
    A step of publishing failed; the message says which and why.
    """


def run_tool(argv: list[str]) -> str:
    """
    Run a command and return its output.

    :param argv: The command.
    :type argv: list[str]
    :return: Its standard output.
    :rtype: str
    :raises PublishError: If it fails or cannot be found.
    """
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=True)
    except FileNotFoundError as error:
        raise PublishError(f"{argv[0]} is not installed") from error
    except subprocess.CalledProcessError as error:
        raise PublishError(
            f"{' '.join(argv)} failed:\n{error.stderr}"
        ) from error
    return done.stdout


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


def project_name(tree: Path) -> str:
    """
    The distribution name in ``pyproject.toml``.

    :param tree: The exported commit.
    :type tree: Path
    :return: e.g. ``afscripts``.
    :rtype: str
    """
    with (tree / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["name"]


def place_catalog(tree: Path, package: str) -> None:
    """
    Put the commit's catalog inside the package, unless it already is.

    :param tree: The exported commit.
    :type tree: Path
    :param package: The package's folder name under ``src``.
    :type package: str
    :raises PublishError: If the commit has no catalog.
    """
    inside = tree / "src" / package / CATALOG_NAME
    beside = tree / CATALOG_NAME
    if inside.is_file():
        return
    if not beside.is_file():
        raise PublishError(f"This commit has no {CATALOG_NAME}")
    shutil.copyfile(beside, inside)


def label_version(tree: Path, commit: str) -> str:
    """
    Add the commit to the version in ``pyproject.toml``.

    :param tree: The exported commit.
    :type tree: Path
    :param commit: The commit.
    :type commit: str
    :return: The new version, e.g. ``0.1.0+g2e6d386``.
    :rtype: str
    :raises PublishError: If the version line cannot be found.
    """
    pyproject = tree / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    version = tomllib.loads(text)["project"]["version"]
    line = f'version = "{version}"'
    if text.count(line) != 1:
        raise PublishError(f"Cannot find '{line}' in pyproject.toml")
    labelled = f"{version}+g{commit[:SHORT_COMMIT]}"
    pyproject.write_text(text.replace(line, f'version = "{labelled}"'))
    return labelled


def build_wheel(tree: Path, out: Path) -> Path:
    """
    Build the wheel with ``uv build``.

    :param tree: The prepared commit.
    :type tree: Path
    :param out: Folder for the wheel.
    :type out: Path
    :return: The wheel.
    :rtype: Path
    :raises PublishError: Unless exactly one wheel was built.
    """
    run_tool(["uv", "build", "--wheel", "--out-dir", str(out), str(tree)])
    wheels = list(out.glob("*.whl"))
    if len(wheels) != 1:
        raise PublishError(f"Expected one wheel, built {len(wheels)}")
    return wheels[0]


def upload(api_url: str, admin_key: str, wheel: Path, commit: str) -> str:
    """
    Publish the wheel and describe what the server did.

    :param api_url: The API's address.
    :type api_url: str
    :param admin_key: The administrator's key.
    :type admin_key: str
    :param wheel: The wheel.
    :type wheel: Path
    :param commit: The commit it was built from.
    :type commit: str
    :return: One line for the person publishing.
    :rtype: str
    :raises PublishError: If the server refused it or was not there.
    """
    try:
        response = httpx.post(
            f"{api_url.rstrip('/')}/api/releases",
            params={"git_commit": commit},
            content=wheel.read_bytes(),
            headers={"X-API-Key": admin_key},
            timeout=UPLOAD_SECONDS,
        )
    except httpx.HTTPError as error:
        raise PublishError(f"Could not reach {api_url}: {error}") from error
    if response.status_code not in (200, 201):
        raise PublishError(f"The API refused it: {response.text}")
    release = response.json()
    label = f"{release['name']} {release['version']}"
    if response.status_code == 200:
        return f"{label} was already published; nothing changed."
    return f"Published {label} (sha256 {release['sha256'][:12]})."


def publish(repo: Path, ref: str, api_url: str, admin_key: str) -> str:
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
    :return: What happened.
    :rtype: str
    """
    commit = resolve_commit(repo, ref)
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch) / "source"
        export_commit(repo, commit, tree)
        place_catalog(tree, package_name(project_name(tree)))
        label_version(tree, commit)
        wheel = build_wheel(tree, Path(scratch) / "dist")
        return upload(api_url, admin_key, wheel, commit)


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
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        print("Error: set ADMIN_API_KEY", file=sys.stderr)
        return 1
    try:
        print(publish(options.repo, options.ref, options.api_url, admin_key))
    except PublishError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
