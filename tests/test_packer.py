"""
What goes into a run's zip: every job folder and run.json, but not
``upstream/`` links (their targets are in the zip already) or hidden
half-written files.
"""

import zipfile
from pathlib import Path

import pytest

from agent.packer import BundleTooLargeError, bundle_files, write_bundle


def make_run(root: Path) -> Path:
    """
    A run folder: ``opt`` with an output, ``md`` linking ``opt``, and a
    half-written download.

    :param root: Empty folder.
    :type root: Path
    :return: The run folder.
    :rtype: Path
    """
    run = root / "run"
    (run / "opt").mkdir(parents=True)
    (run / "opt" / "opt.xyz").write_text("opt")
    (run / "md" / "upstream").mkdir(parents=True)
    (run / "md" / "upstream" / "opt").symlink_to("../../opt")
    (run / "md" / "traj.xyz").write_text("traj")
    (run / "md" / ".water.xyz.part").write_text("partial")
    return run


def test_links_and_hidden_files_stay_out(tmp_path: Path):
    """
    Only real files are zipped, each once.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    run = make_run(tmp_path)
    found = [path.relative_to(run).as_posix() for path in bundle_files(run)]
    assert found == ["md/traj.xyz", "opt/opt.xyz"]


def test_the_zip_holds_run_json_under_one_top_folder(tmp_path: Path):
    """
    Unzipping gives one folder named like the zip, with run.json.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    run = make_run(tmp_path)
    destination = tmp_path / "bundle.zip"
    size = write_bundle(run, "water_r1", {"jobs": []}, destination, 10**6)

    names = zipfile.ZipFile(destination).namelist()
    assert size == destination.stat().st_size
    assert names == [
        "water_r1/run.json",
        "water_r1/md/traj.xyz",
        "water_r1/opt/opt.xyz",
    ]


def test_writing_stops_once_past_the_limit(tmp_path: Path):
    """
    A run too big to upload is not zipped in full.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    run = make_run(tmp_path)
    with pytest.raises(BundleTooLargeError):
        write_bundle(run, "water_r1", {}, tmp_path / "bundle.zip", 10)
