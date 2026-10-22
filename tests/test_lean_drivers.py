"""
Tests for the lean driver integration: upstream workspace symlinking,
driver detection, command building, and filesystem discovery.
"""

import os
import tempfile
from pathlib import Path

import pytest

from app.worker.tasks import (
    _build_chemistry_command,
    _is_chemistry_task,
    _link_upstream_workspaces,
)

DRIVER_MODULES = [
    ("xtb_opt", "afscripts.scripts.xtbopt_driver"),
    ("xtbopt_driver.py", "afscripts.scripts.xtbopt_driver"),
    ("xtb_md", "afscripts.scripts.xtbmd_driver"),
    ("rxn_network", "afscripts.scripts.rxn_network_driver"),
    ("mlff_refine", "afscripts.scripts.mlff_refine_driver"),
    ("ts_search", "afscripts.scripts.ts_search_driver"),
    ("other_script.py", None),
]


@pytest.mark.parametrize(("script_name", "expected_module"), DRIVER_MODULES)
def test_is_chemistry_task(script_name: str, expected_module: str | None):
    """
    Lean driver names resolve to their module; other scripts do not.

    :param script_name: Script or node name to resolve.
    :type script_name: str
    :param expected_module: Module path, or None for non-chemistry.
    :type expected_module: str | None
    """
    assert _is_chemistry_task(script_name) == expected_module


def test_link_upstream_workspaces():
    """
    A parent's workspace is symlinked into the child's upstream folder.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir)
        parent_dir = session_dir / "job_parent-uuid"
        parent_dir.mkdir()
        (parent_dir / "reactant_optimized.xyz").write_text("dummy xyz")
        (parent_dir / "xtb_opt.log").write_text("opt log content")
        child_dir = session_dir / "job_child-uuid"
        child_dir.mkdir()
        params = {
            "upstream_results": {
                "parent-uuid": {"status": "simulation_complete"}
            }
        }

        _link_upstream_workspaces(session_dir, child_dir, params)

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
        job_b.mkdir()
        (job_b / "traj.xyz").write_text("traj")
        (job_b / "upstream").mkdir()
        (job_b / "upstream" / "job_aaa").symlink_to(
            job_a.resolve(), target_is_directory=True
        )

        job_c = session_dir / "job_ccc"
        job_c.mkdir()
        params = {"upstream_results": {"bbb": {"status": "success"}}}
        _link_upstream_workspaces(session_dir, job_c, params)

        upstream_c = job_c / "upstream"
        assert (upstream_c / "job_bbb").is_symlink()
        assert (upstream_c / "job_aaa").is_symlink()
        assert (upstream_c / "job_aaa" / "opt.xyz").exists()
        assert (upstream_c / "job_bbb" / "traj.xyz").exists()


def test_find_upstream_files_follows_symlinks():
    """
    ``find_upstream_files`` traverses symlinks in ``upstream/``.

    Skipped where afscripts is not installed: CI cannot clone the
    ``scripts_repo`` submodule, which points to a local path.
    """
    fileutils = pytest.importorskip("afscripts.utilities.fileutils")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        parent_dir = root / "parent"
        parent_dir.mkdir()
        (parent_dir / "mol1_optimized.xyz").write_text("xyz")
        (parent_dir / "raw_network.json").write_text("{}")
        upstream_dir = root / "child" / "upstream"
        upstream_dir.mkdir(parents=True)
        (upstream_dir / "parent").symlink_to(
            parent_dir.resolve(), target_is_directory=True
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(root / "child")
            found_xyz = fileutils.find_upstream_files("*.xyz")
            found_json = fileutils.find_upstream_files("*.json")
        finally:
            os.chdir(original_cwd)
        assert [path.name for path in found_xyz] == ["mol1_optimized.xyz"]
        assert [path.name for path in found_json] == ["raw_network.json"]


def test_build_chemistry_command():
    """
    Parameters become CLI arguments; internal parameters are dropped.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        (workspace / "start.xyz").write_text("xyz")
        params = {
            "pipeline_id": "test_pipe",
            "user_id": "u1",
            "upstream_results": {"p1": {}},
            "temp": 1200.0,
            "time": 0.5,
            "skip_mtd": True,
            "input": "start.xyz",
        }

        command = _build_chemistry_command(
            "python3",
            "afscripts.scripts.xtbmd_driver",
            "xtb_md",
            workspace,
            params,
        )

        assert command[:4] == [
            "python3",
            "-u",
            "-m",
            "afscripts.scripts.xtbmd_driver",
        ]
        expected_tokens = ["-temp", "1200.0", "-time", "0.5", "-skip_mtd"]
        expected_tokens += ["-i", str(workspace / "start.xyz")]
        expected_tokens += ["-JOBNAME", "xtb_md"]
        assert set(expected_tokens) <= set(command)
        assert "test_pipe" not in command
        assert "u1" not in command
