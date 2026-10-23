"""
Job folders: a child sees its parents' (and their ancestors') files
through ``upstream/`` links, and afscripts can find them there.
"""

import os
import tempfile
from pathlib import Path

import pytest

from agent.workspace import link_upstream_workspaces


def test_link_upstream_workspaces():
    """
    A parent's workspace is symlinked into the child's upstream folder.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir)
        parent_dir = session_dir / "job_parent-uuid"
        parent_dir.mkdir()
        (parent_dir / "reactant_optimized.xyz").write_text("dummy xyz")
        child_dir = session_dir / "job_child-uuid"
        child_dir.mkdir()
        params = {"upstream_results": {"parent-uuid": {"status": "done"}}}

        link_upstream_workspaces(session_dir, child_dir, params)

        upstream_link = child_dir / "upstream" / "job_parent-uuid"
        assert upstream_link.is_symlink()
        linked_file = upstream_link / "reactant_optimized.xyz"
        assert linked_file.read_text() == "dummy xyz"


def test_link_upstream_transitive_ancestors():
    """
    Ancestors linked into a parent's upstream folder reach the child.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir)
        job_a = session_dir / "job_aaa"
        job_a.mkdir()
        (job_a / "opt.xyz").write_text("opt")
        job_b = session_dir / "job_bbb"
        (job_b / "upstream").mkdir(parents=True)
        (job_b / "traj.xyz").write_text("traj")
        (job_b / "upstream" / "job_aaa").symlink_to(
            job_a.resolve(), target_is_directory=True
        )
        job_c = session_dir / "job_ccc"
        job_c.mkdir()
        params = {"upstream_results": {"bbb": {"status": "success"}}}

        link_upstream_workspaces(session_dir, job_c, params)

        upstream_c = job_c / "upstream"
        assert (upstream_c / "job_aaa" / "opt.xyz").exists()
        assert (upstream_c / "job_bbb" / "traj.xyz").exists()


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
