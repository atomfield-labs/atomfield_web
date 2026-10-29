"""
Job folders: a child sees its parents' (and their ancestors') files
through ``upstream/`` links named after their nodes, and afscripts can
find them there.
"""

import os
import tempfile
from pathlib import Path

import pytest

from agent.workspace import link_parents, success_output


def test_a_parent_folder_is_linked_under_upstream(tmp_path: Path):
    """
    A parent's folder is symlinked into the child's ``upstream/``,
    named after the parent's node.

    :param tmp_path: Empty run folder.
    :type tmp_path: Path
    """
    (tmp_path / "opt").mkdir()
    (tmp_path / "opt" / "water_optimized.xyz").write_text("xyz")
    child = tmp_path / "md"
    child.mkdir()

    link_parents(tmp_path, child, ["opt"])

    link = child / "upstream" / "opt"
    assert link.is_symlink()
    assert os.readlink(link) == "../../opt"
    assert (link / "water_optimized.xyz").read_text() == "xyz"


def test_links_still_work_after_the_run_folder_moves(tmp_path: Path):
    """
    Copying a run folder elsewhere (rsync to a laptop) keeps its
    ``upstream/`` links working, because they are relative.

    :param tmp_path: Empty folder holding the run.
    :type tmp_path: Path
    """
    run = tmp_path / "cluster" / "run"
    for name in ("opt", "md"):
        (run / name).mkdir(parents=True)
    (run / "opt" / "opt.xyz").write_text("opt")
    link_parents(run, run / "md", ["opt"])

    moved = tmp_path / "laptop" / "run"
    moved.parent.mkdir()
    run.rename(moved)

    assert (moved / "md" / "upstream" / "opt" / "opt.xyz").read_text() == "opt"


def test_ancestors_reach_the_child_through_the_parent(tmp_path: Path):
    """
    Grandparents linked into a parent's ``upstream/`` reach the child.

    :param tmp_path: Empty run folder.
    :type tmp_path: Path
    """
    for name in ("opt", "md", "analysis"):
        (tmp_path / name).mkdir()
    (tmp_path / "opt" / "opt.xyz").write_text("opt")
    (tmp_path / "md" / "traj.xyz").write_text("traj")
    link_parents(tmp_path, tmp_path / "md", ["opt"])

    link_parents(tmp_path, tmp_path / "analysis", ["md"])

    upstream = tmp_path / "analysis" / "upstream"
    assert (upstream / "opt" / "opt.xyz").exists()
    assert (upstream / "md" / "traj.xyz").exists()


@pytest.mark.parametrize("name", ["../escape", "a/b", "..", ""])
def test_a_parent_name_cannot_be_a_path(name: str, tmp_path: Path):
    """
    Names from the server are folder names, never paths.

    :param name: A path-like parent name.
    :type name: str
    :param tmp_path: Empty run folder.
    :type tmp_path: Path
    """
    (tmp_path / "md").mkdir()
    with pytest.raises(ValueError):
        link_parents(tmp_path, tmp_path / "md", [name])


def test_find_upstream_files_follows_symlinks():
    """
    afscripts' ``find_upstream_files`` traverses ``upstream/`` links.

    Skipped where afscripts is not installed: CI cannot clone the
    ``scripts_repo`` submodule, which points to a local path.
    """
    fileutils = pytest.importorskip("afscripts.utilities.fileutils")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        parent_dir = root / "parent"
        parent_dir.mkdir()
        (parent_dir / "mol1_optimized.xyz").write_text("xyz")
        upstream_dir = root / "child" / "upstream"
        upstream_dir.mkdir(parents=True)
        (upstream_dir / "parent").symlink_to(
            parent_dir.resolve(), target_is_directory=True
        )
        original_cwd = os.getcwd()
        try:
            os.chdir(root / "child")
            found = fileutils.find_upstream_files("*.xyz")
        finally:
            os.chdir(original_cwd)
        assert [path.name for path in found] == ["mol1_optimized.xyz"]


def test_a_link_to_a_parent_file_is_not_listed_as_an_output(
    tmp_path: Path,
):
    """
    A later step that links an earlier step's file (postw90 reading
    Wannier90's checkpoint) lists only what it wrote itself.

    :param tmp_path: Empty run folder.
    :type tmp_path: Path
    """
    (tmp_path / "wannier").mkdir()
    (tmp_path / "wannier" / "fe.chk").write_text("checkpoint")
    berry = tmp_path / "berry"
    berry.mkdir()
    (berry / "fe.chk").symlink_to(Path("..") / "wannier" / "fe.chk")
    (berry / "results.csv").write_text("sigma_xy,750")

    output = success_output("ahc_berry", berry, "pipeline", "job")

    assert output["artifacts"] == ["results.csv"]
