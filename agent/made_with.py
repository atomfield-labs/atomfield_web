"""
The note each job folder gets, ``.af_made_with``: exactly which
scripts and data packs the job ran with. Results copied anywhere
still say what made them.
"""

import json
from pathlib import Path

from app.agents.schemas import DataRef, ReleaseRef

MADE_WITH_NOTE = ".af_made_with"


def scripts_entry(folder: Path, release: ReleaseRef | None) -> dict:
    """
    Describe the scripts a job ran.

    :param folder: The scripts' folder (put on ``PYTHONPATH``).
    :type folder: Path
    :param release: The release, or None for the owner's own copy.
    :type release: ReleaseRef | None
    :return: The description.
    :rtype: dict
    """
    if release is None:
        return {"source": "own copy", "folder": str(folder)}
    return {
        "source": "release",
        "name": release.name,
        "version": release.version,
        "sha256": release.sha256,
        "folder": str(folder),
    }


def data_entry(pack: DataRef, folder: Path) -> dict:
    """
    Describe one data pack a job read.

    :param pack: The pack.
    :type pack: DataRef
    :param folder: Where it was unpacked.
    :type folder: Path
    :return: The description.
    :rtype: dict
    """
    return {
        "name": pack.name,
        "version": pack.version,
        "sha256": pack.sha256,
        "env": pack.env,
        "folder": str(folder),
    }


def write_made_with(
    workspace: Path,
    scripts: dict,
    packs: list[DataRef],
    folders: dict[str, Path],
) -> None:
    """
    Write the note into a job's folder.

    :param workspace: The job's folder.
    :type workspace: Path
    :param scripts: From ``scripts_entry``.
    :type scripts: dict
    :param packs: The job's data packs.
    :type packs: list[DataRef]
    :param folders: Variable -> unpacked folder, for each pack.
    :type folders: dict[str, Path]
    """
    note = {
        "scripts": scripts,
        "data": [data_entry(pack, folders[pack.env]) for pack in packs],
    }
    (workspace / MADE_WITH_NOTE).write_text(json.dumps(note, indent=2))
