"""
Scripts releases for tests: real bundles (zip files) holding the fake
pack's driver as package ``toy``, one wheel per fixture workflow,
built in memory without any build tool.
"""

import io
import json
import zipfile
from pathlib import Path

from app.core.machines import ANY
from app.releases.bundle import CATALOG_NAME, MANIFEST_NAME
from tests.fake_pack import FAKE_DRIVER

FIXTURE_CATALOG = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
# What each fixture workflow's wheel holds, its tasks' modules.
PACKAGE_FILES = {
    "toy_chain": {
        "toy/__init__.py": "",
        "toy/opt_driver.py": FAKE_DRIVER,
        "toy/network_driver.py": "",
    },
    "toy_other": {
        "toy/__init__.py": "",
        "toy/solo_driver.py": "",
    },
}
WHEEL_FILE_PREFIX = "toy/"
# Says which wheel an agent was given.
BUILT_FOR = "toy/built_for.txt"
# Fixed timestamps: the same files always make the same bytes.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def zipped(files: dict[str, str | bytes | None]) -> bytes:
    """
    A zip file holding these files, the same bytes every time.

    :param files: Path -> content; None leaves the file out.
    :type files: dict[str, str | bytes | None]
    :return: The zip's bytes.
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in sorted(files.items()):
            if content is not None:
                archive.writestr(zipfile.ZipInfo(name, ZIP_TIME), content)
    return buffer.getvalue()


def make_wheel(
    package: str = "toy_chain",
    machine: str = ANY,
    replace: dict[str, str | None] | None = None,
) -> bytes:
    """
    One package's wheel.

    :param package: Which fixture workflow.
    :type package: str
    :param machine: The machine it says it is for.
    :type machine: str
    :param replace: Files to change (None removes the file).
    :type replace: dict[str, str | None] | None
    :return: The wheel's bytes.
    :rtype: bytes
    """
    built_for = {BUILT_FOR: f"{package} {machine}"}
    changed = {
        name: content
        for name, content in (replace or {}).items()
        if name.startswith(WHEEL_FILE_PREFIX)
    }
    return zipped({**PACKAGE_FILES[package], **built_for, **changed})


def manifest(version: str, machines: tuple[str, ...]) -> str:
    """
    The ``release.json`` of a ``toy`` release.

    :param version: Its version.
    :type version: str
    :param machines: The machines it has wheels for.
    :type machines: tuple[str, ...]
    :return: The manifest as JSON.
    :rtype: str
    """
    wheels = [
        {
            "package": package,
            "machine": machine,
            "file": f"{package}-{machine}.whl",
        }
        for package in PACKAGE_FILES
        for machine in machines
    ]
    return json.dumps({"name": "toy", "version": version, "wheels": wheels})


def make_release(
    version: str = "1.0.0",
    replace: dict[str, str | None] | None = None,
    machines: tuple[str, ...] = (ANY,),
) -> bytes:
    """
    A release bundle.

    :param version: Its version.
    :type version: str
    :param replace: Files to change: ``toy/...`` in every wheel, the
        rest in the bundle (None removes the file).
    :type replace: dict[str, str | None] | None
    :param machines: The machines it has wheels for.
    :type machines: tuple[str, ...]
    :return: The bundle's bytes.
    :rtype: bytes
    """
    files: dict[str, str | bytes | None] = {
        MANIFEST_NAME: manifest(version, machines),
        CATALOG_NAME: FIXTURE_CATALOG.read_text(),
    }
    for package in PACKAGE_FILES:
        for machine in machines:
            wheel = make_wheel(package, machine, replace)
            files[f"{package}-{machine}.whl"] = wheel
    bundle_changes = {
        name: content
        for name, content in (replace or {}).items()
        if not name.startswith(WHEEL_FILE_PREFIX)
    }
    return zipped({**files, **bundle_changes})
