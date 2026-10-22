"""
Tests for running catalog tasks: workspace preparation and real
subprocess runs against a tiny fake pack (no chemistry needed).
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from app.catalog.catalog import Catalog
from app.core.config import settings
from app.worker import execution
from app.worker.execution import link_upstream_workspaces, run_catalog_task

FAKE_DRIVER = """
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("-i", dest="input")
parser.add_argument("-JOBNAME", dest="jobname")
parser.add_argument("-parallel", dest="parallel", type=int)
parser.add_argument("-charge", dest="charge", type=int, default=0)
parser.add_argument("-temp", dest="temp", type=float, default=300.0)
parser.add_argument("-gfnff", dest="gfnff", action="store_true")
parser.add_argument("-nokeep", dest="keep", action="store_false")
parser.add_argument("-optlevel", dest="optlevel", default="normal")
parser.add_argument("-gfn", dest="gfn", type=int, default=2)
parser.add_argument("-solvent", dest="solvent")
options = parser.parse_args()
if options.charge < 0:
    print("negative charge refused", file=sys.stderr)
    sys.exit(3)
with open(f"{options.jobname}_optimized.xyz", "w") as out:
    out.write(open(options.input).read())
with open("received.json", "w") as out:
    json.dump(vars(options), out)
"""
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"


@pytest.fixture
def fake_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Install a one-module pack named ``toy`` and run tasks in tmp_path.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    :param monkeypatch: Points the worker at the fake pack.
    :type monkeypatch: pytest.MonkeyPatch
    :return: Directory where job workspaces are created.
    :rtype: Path
    """
    package = tmp_path / "pack" / "toy"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "opt_driver.py").write_text(FAKE_DRIVER)
    monkeypatch.setattr(execution, "PACK_SOURCE_DIR", tmp_path / "pack")
    monkeypatch.setattr(settings, "CHEMISTRY_PYTHON_BIN", sys.executable)
    monkeypatch.setattr(settings, "ARTIFACTS_DIR", str(tmp_path / "jobs"))
    session = tmp_path / "jobs" / "user_1" / "session_1"
    session.mkdir(parents=True)
    (session / "water.xyz").write_text("3\nwater\nO 0 0 0\n")
    return session


def toy_parameters(catalog: Catalog, **values) -> dict:
    """
    Validate toy_opt values and add the bookkeeping a job carries.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    :param values: Parameter values to set.
    :type values: Any
    :return: Stored-job style parameters.
    :rtype: dict
    """
    validated = catalog.validate_values("toy_opt", values)
    return {**validated, "pipeline_id": "session_1", "user_id": "user_1"}


def test_task_runs_with_exactly_the_declared_command(fake_pack: Path):
    """
    The script receives the validated values, its input file and the
    platform flags, and nothing else; outputs are listed afterwards.

    :param fake_pack: Session folder of the fake pack's jobs.
    :type fake_pack: Path
    """
    catalog = Catalog.from_path(FIXTURE)
    parameters = toy_parameters(catalog, charge=1, gfnff=True)

    result = run_catalog_task(
        catalog.get("toy_opt"),
        parameters,
        {"structure": ["water.xyz"]},
        "42",
    )

    assert result["status"] == "success", result
    assert "toy_opt_optimized.xyz" in result["output"]["artifacts"]
    received = json.loads((fake_pack / "job_42" / "received.json").read_text())
    assert received["input"] == "water.xyz"
    assert received["jobname"] == "toy_opt"
    assert received["parallel"] == 2
    assert received["charge"] == 1
    assert received["gfnff"] is True
    assert received["keep"] is True


def test_failed_run_reports_the_script_output(fake_pack: Path):
    """
    A non-zero exit becomes a failure carrying the script's own output.

    :param fake_pack: Session folder of the fake pack's jobs.
    :type fake_pack: Path
    """
    catalog = Catalog.from_path(FIXTURE)
    parameters = toy_parameters(catalog, charge=-1)

    result = run_catalog_task(
        catalog.get("toy_opt"),
        parameters,
        {"structure": ["water.xyz"]},
        "43",
    )

    assert result["status"] == "failed"
    assert "toy_opt failed (code 3)" in result["error"]
    assert "negative charge refused" in result["error"]


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
