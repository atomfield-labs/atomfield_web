"""
Tests for 5 Lean Drivers integration: upstream workspace symlinking,
driver detection, command building, and filesystem discovery.
"""

import os
import tempfile
from pathlib import Path

from afscripts.utilities.fileutils import find_upstream_files
from app.worker.tasks import (
    _build_chemistry_command,
    _is_chemistry_task,
    _link_upstream_workspaces,
)



def test_is_chemistry_task():
    """Verify that lean driver names are correctly identified as chemistry tasks."""
    assert _is_chemistry_task("xtb_opt") == "afscripts.scripts.xtbopt_driver"
    assert _is_chemistry_task("xtbopt_driver.py") == "afscripts.scripts.xtbopt_driver"
    assert _is_chemistry_task("xtb_md") == "afscripts.scripts.xtbmd_driver"
    assert _is_chemistry_task("rxn_network") == "afscripts.scripts.rxn_network_driver"
    assert _is_chemistry_task("mlff_refine") == "afscripts.scripts.mlff_refine_driver"
    assert _is_chemistry_task("ts_search") == "afscripts.scripts.ts_search_driver"
    assert _is_chemistry_task("other_script.py") is None


def test_link_upstream_workspaces():
    """Verify that parent workspace directories are symlinked into child's upstream folder."""
    with tempfile.TemporaryDirectory() as td:
        session_dir = Path(td)
        parent_dir = session_dir / "job_parent-uuid"
        parent_dir.mkdir()
        (parent_dir / "reactant_optimized.xyz").write_text("dummy xyz content")
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
        assert upstream_link.exists()
        assert upstream_link.is_symlink()
        assert (upstream_link / "reactant_optimized.xyz").exists()
        assert (
            (upstream_link / "reactant_optimized.xyz").read_text()
            == "dummy xyz content"
        )


def test_link_upstream_transitive_ancestors():
    """Verify that ancestor workspaces from parent's upstream are also accessible."""
    with tempfile.TemporaryDirectory() as td:
        session_dir = Path(td)

        # Ancestor job A (e.g. xtb_opt)
        job_a = session_dir / "job_aaa"
        job_a.mkdir()
        (job_a / "opt.xyz").write_text("opt")

        # Parent job B (e.g. xtb_md) with upstream/job_aaa
        job_b = session_dir / "job_bbb"
        job_b.mkdir()
        (job_b / "traj.xyz").write_text("traj")
        up_b = job_b / "upstream"
        up_b.mkdir()
        (up_b / "job_aaa").symlink_to(job_a.resolve(), target_is_directory=True)

        # Child job C (e.g. rxn_network) with parent B
        job_c = session_dir / "job_ccc"
        job_c.mkdir()

        params = {"upstream_results": {"bbb": {"status": "success"}}}
        _link_upstream_workspaces(session_dir, job_c, params)

        up_c = job_c / "upstream"
        assert (up_c / "job_bbb").is_symlink()
        assert (up_c / "job_aaa").is_symlink()
        assert (up_c / "job_aaa" / "opt.xyz").exists()
        assert (up_c / "job_bbb" / "traj.xyz").exists()


def test_find_upstream_files_follows_symlinks():
    """Verify find_upstream_files traverses symlinks in upstream/ directory."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        parent_dir = root / "parent"
        parent_dir.mkdir()
        (parent_dir / "mol1_optimized.xyz").write_text("xyz")
        (parent_dir / "raw_network.json").write_text("{}")

        child_dir = root / "child"
        child_dir.mkdir()
        up_dir = child_dir / "upstream"
        up_dir.mkdir()
        (up_dir / "parent").symlink_to(parent_dir.resolve(), target_is_directory=True)

        orig_cwd = os.getcwd()
        try:
            os.chdir(child_dir)
            found_xyz = find_upstream_files("*.xyz")
            found_json = find_upstream_files("*.json")
            assert len(found_xyz) == 1
            assert found_xyz[0].name == "mol1_optimized.xyz"
            assert len(found_json) == 1
            assert found_json[0].name == "raw_network.json"
        finally:
            os.chdir(orig_cwd)


def test_build_chemistry_command():
    """Verify that parameters are transformed into valid CLI arguments."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "start.xyz").write_text("xyz")

        params = {
            "pipeline_id": "test_pipe",
            "user_id": "u1",
            "upstream_results": {"p1": {}},
            "temp": 1200.0,
            "time": 0.5,
            "skip_mtd": True,
            "input": "start.xyz",
        }

        cmd = _build_chemistry_command(
            "python3", "afscripts.scripts.xtbmd_driver", "xtb_md", ws, params
        )

        assert cmd[0] == "python3"
        assert cmd[1:4] == ["-u", "-m", "afscripts.scripts.xtbmd_driver"]
        assert "-temp" in cmd
        assert "1200.0" in cmd
        assert "-time" in cmd
        assert "0.5" in cmd
        assert "-skip_mtd" in cmd
        assert "-i" in cmd
        assert str(ws / "start.xyz") in cmd
        assert "-JOBNAME" in cmd
        assert "xtb_md" in cmd
        # Internal params must not appear
        assert "test_pipe" not in cmd
        assert "u1" not in cmd
