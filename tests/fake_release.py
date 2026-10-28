"""
Scripts releases for tests: real wheels (zip files) holding the fake
pack's driver as package ``toy`` with the fixture catalog inside,
built in memory without any build tool.
"""

import io
import zipfile
from pathlib import Path

from tests.fake_pack import FAKE_DRIVER

FIXTURE_CATALOG = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
PURE_WHEEL = (
    "Wheel-Version: 1.0\nGenerator: tests\n"
    "Root-Is-Purelib: true\nTag: py3-none-any\n"
)
# Fixed timestamps: the same files always make the same bytes.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def release_files(version: str) -> dict[str, str]:
    """
    The files of a ``toy`` release.

    :param version: Its version.
    :type version: str
    :return: Path in the wheel -> content.
    :rtype: dict[str, str]
    """
    dist_info = f"toy-{version}.dist-info"
    metadata = f"Metadata-Version: 2.3\nName: toy\nVersion: {version}\n"
    return {
        "toy/__init__.py": "",
        "toy/opt_driver.py": FAKE_DRIVER,
        "toy/network_driver.py": "",
        "toy/catalog.json": FIXTURE_CATALOG.read_text(),
        f"{dist_info}/METADATA": metadata,
        f"{dist_info}/WHEEL": PURE_WHEEL,
        f"{dist_info}/RECORD": "",
    }


def make_release(
    version: str = "1.0.0",
    replace: dict[str, str | None] | None = None,
) -> bytes:
    """
    A release wheel.

    :param version: Its version.
    :type version: str
    :param replace: Files to change (None removes the file).
    :type replace: dict[str, str | None] | None
    :return: The wheel's bytes.
    :rtype: bytes
    """
    files = {**release_files(version), **(replace or {})}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in sorted(files.items()):
            if content is not None:
                archive.writestr(zipfile.ZipInfo(name, ZIP_TIME), content)
    return buffer.getvalue()
