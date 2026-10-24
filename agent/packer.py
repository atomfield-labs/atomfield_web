"""
Zip a run's folder for download: every job folder (inputs, outputs,
logs) plus ``run.json``, under one top folder named like the zip.

``upstream/`` links are left out (they point at sibling folders that
are in the zip anyway) and so are hidden files (half-written
downloads). Writing stops as soon as the zip grows past its limit, so
a run far too big to upload is not zipped in full just to find out.
"""

import json
import os
import zipfile
from pathlib import Path
from typing import Any

UPSTREAM_DIR = "upstream"
MANIFEST_NAME = "run.json"


class BundleTooLargeError(Exception):
    """
    The zip grew past the size the server accepts.
    """

    def __init__(self, size_bytes: int) -> None:
        """
        :param size_bytes: Size reached when writing stopped.
        :type size_bytes: int
        """
        super().__init__(f"Zip passed its limit at {size_bytes} bytes")
        self.size_bytes = size_bytes


def bundle_files(run_dir: Path) -> list[Path]:
    """
    Every file to zip, skipping ``upstream/`` links and hidden files.

    :param run_dir: The run's folder.
    :type run_dir: Path
    :return: Files, sorted.
    :rtype: list[Path]
    """
    found = []
    for folder, subfolders, names in os.walk(run_dir):
        subfolders[:] = [
            name
            for name in subfolders
            if name != UPSTREAM_DIR and not name.startswith(".")
        ]
        for name in names:
            path = Path(folder) / name
            if not name.startswith(".") and not path.is_symlink():
                found.append(path)
    return sorted(found)


def write_bundle(
    run_dir: Path,
    top_folder: str,
    manifest: dict[str, Any],
    destination: Path,
    max_bytes: int,
) -> int:
    """
    Zip a run folder into ``destination``.

    :param run_dir: The run's folder.
    :type run_dir: Path
    :param top_folder: Folder name inside the zip.
    :type top_folder: str
    :param manifest: Written as ``run.json``.
    :type manifest: dict[str, Any]
    :param destination: The zip to create.
    :type destination: Path
    :param max_bytes: Largest zip the server accepts.
    :type max_bytes: int
    :return: Size of the finished zip.
    :rtype: int
    :raises BundleTooLargeError: As soon as the zip passes the limit.
    """
    options = {"compression": zipfile.ZIP_DEFLATED, "allowZip64": True}
    with zipfile.ZipFile(destination, "w", **options) as archive:
        archive.writestr(
            f"{top_folder}/{MANIFEST_NAME}", json.dumps(manifest, indent=2)
        )
        for path in bundle_files(run_dir):
            relative = path.relative_to(run_dir).as_posix()
            archive.write(path, f"{top_folder}/{relative}")
            if destination.stat().st_size > max_bytes:
                raise BundleTooLargeError(destination.stat().st_size)
    size = destination.stat().st_size
    if size > max_bytes:
        raise BundleTooLargeError(size)
    return size
