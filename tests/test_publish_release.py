"""
The publish commands. A release is built from exactly one git commit:
never unfinished files from the working folder, with the commit's
catalog inside the package and the commit in the version. A data pack
folder zips to the same bytes every time.
"""

import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

from app.releases.publish import (
    PublishError,
    export_commit,
    label_version,
    place_catalog,
    resolve_commit,
)
from app.releases.publish_data import check_zip, prepare_zip

PYPROJECT = '[project]\nname = "toy"\nversion = "1.0.0"\n'
COMMITTED_DRIVER = "print('committed')\n"


def git(repo: Path, *arguments: str) -> None:
    """
    Run git in a test repository, as a throwaway identity.

    :param repo: The repository.
    :type repo: Path
    :param arguments: Git arguments.
    :type arguments: str
    """
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.org"]
    subprocess.run(
        ["git", "-C", str(repo), *identity, *arguments],
        check=True,
        capture_output=True,
    )


def scripts_repo(root: Path, with_catalog: bool = True) -> Path:
    """
    A one-commit scripts repository, then unfinished work on top: a
    changed driver and a new file, neither committed.

    :param root: Folder to create it in.
    :type root: Path
    :param with_catalog: Commit a ``catalog.json`` beside the package.
    :type with_catalog: bool
    :return: The repository.
    :rtype: Path
    """
    repo = root / "afscripts"
    package = repo / "src" / "toy"
    package.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(PYPROJECT)
    (package / "__init__.py").write_text("")
    (package / "opt_driver.py").write_text(COMMITTED_DRIVER)
    if with_catalog:
        (repo / "catalog.json").write_text('{"format_version": 1}')
    git(repo, "init", "--quiet")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "first")
    (package / "opt_driver.py").write_text("print('unfinished')\n")
    (package / "wip.py").write_text("")
    return repo


def test_only_the_commit_ships_with_its_catalog_inside(tmp_path: Path):
    """
    Unfinished work stays behind; the catalog goes inside the
    package; the version names the commit.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    repo = scripts_repo(tmp_path)
    commit = resolve_commit(repo, "HEAD")
    tree = tmp_path / "build" / "source"
    tree.parent.mkdir()
    export_commit(repo, commit, tree)
    place_catalog(tree, "toy")
    version = label_version(tree, commit)

    package = tree / "src" / "toy"
    assert (package / "opt_driver.py").read_text() == COMMITTED_DRIVER
    assert not (package / "wip.py").exists()
    assert (package / "catalog.json").is_file()
    assert version == f"1.0.0+g{commit[:7]}"
    pyproject = tomllib.loads((tree / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == version


def test_a_commit_without_a_catalog_is_not_published(tmp_path: Path):
    """
    Without its catalog, a release could not say what it runs.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    repo = scripts_repo(tmp_path, with_catalog=False)
    tree = tmp_path / "build" / "source"
    tree.parent.mkdir()
    export_commit(repo, resolve_commit(repo, "HEAD"), tree)
    with pytest.raises(PublishError, match="no catalog.json"):
        place_catalog(tree, "toy")
    with pytest.raises(PublishError, match="failed"):
        resolve_commit(repo, "no-such-branch")


def test_a_folder_becomes_the_same_zip_every_time(tmp_path: Path):
    """
    The same files always zip to the same bytes (so publishing them
    again changes nothing); hidden files are left out; only sound zips
    are accepted.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    folder = tmp_path / "pslibrary-rel-pbe"
    (folder / "extra").mkdir(parents=True)
    (folder / "Fe.rel-pbe-n-kjpaw_psl.1.0.0.UPF").write_text("<UPF/>\n")
    (folder / "extra" / "O.UPF").write_text("<UPF/>\n")
    (folder / ".DS_Store").write_text("finder noise")
    scratch = [tmp_path / "one", tmp_path / "two"]
    for place in scratch:
        place.mkdir()
    first, second = (prepare_zip(folder, place) for place in scratch)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            "Fe.rel-pbe-n-kjpaw_psl.1.0.0.UPF",
            "extra/O.UPF",
        ]
    not_a_zip = tmp_path / "notes.txt"
    not_a_zip.write_text("plain text")
    with pytest.raises(PublishError, match="not a zip"):
        check_zip(not_a_zip)
