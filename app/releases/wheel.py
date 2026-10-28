"""
Read a release, a pure-Python wheel, without running any of it: its
name, version and fingerprint, and the catalog packed inside it.

A wheel is the zip file a Python package ships as: the package's
files plus a ``<name>-<version>.dist-info`` folder describing it. A
release must also:

- be pure Python for any machine, since agents simply unzip it onto
  ``PYTHONPATH``;
- carry its catalog as ``<package>/catalog.json``, so code and catalog
  can never be separated;
- contain every module its catalog names, so no task can point at
  code that is not there.
"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from email.message import Message
from email.parser import HeaderParser

from app.catalog.catalog import Catalog
from app.catalog.models import PACKAGE_NAME_PATTERN, CatalogDocument

CATALOG_NAME = "catalog.json"
DIST_INFO_SUFFIX = ".dist-info"
PURE_PYTHON_TAG = "py3-none-any"
MAX_RELEASE_BYTES = 20 * 1024 * 1024
SAFE_NAME = re.compile(PACKAGE_NAME_PATTERN)


class InvalidReleaseError(ValueError):
    """
    The file is not a release agents can run.
    """


@dataclass(frozen=True, slots=True)
class ReleaseContents:
    """
    What a valid release holds.

    :param name: Distribution name, e.g. ``afscripts``.
    :type name: str
    :param version: Its version, e.g. ``0.2.0+g2e6d386``.
    :type version: str
    :param sha256: Fingerprint of the whole file, in hex.
    :type sha256: str
    :param catalog: The tasks it provides.
    :type catalog: CatalogDocument
    """

    name: str
    version: str
    sha256: str
    catalog: CatalogDocument


def read_release(data: bytes) -> ReleaseContents:
    """
    Check a wheel and read what it holds.

    :param data: The wheel file.
    :type data: bytes
    :return: Its name, version, fingerprint and catalog.
    :rtype: ReleaseContents
    :raises InvalidReleaseError: If agents could not run it.
    """
    if len(data) > MAX_RELEASE_BYTES:
        raise InvalidReleaseError(
            f"A release may be at most {MAX_RELEASE_BYTES} bytes"
        )
    archive = open_wheel(data)
    require_pure_python(wheel_fields(archive, "WHEEL"))
    metadata = wheel_fields(archive, "METADATA")
    name = safe_name(metadata.get("Name", ""))
    version = safe_name(metadata.get("Version", ""))
    catalog = read_catalog(archive, package_name(name))
    require_modules(archive.namelist(), catalog)
    fingerprint = hashlib.sha256(data).hexdigest()
    return ReleaseContents(name, version, fingerprint, catalog)


def open_wheel(data: bytes) -> zipfile.ZipFile:
    """
    Open a wheel's bytes as the zip file it is.

    :param data: The wheel file.
    :type data: bytes
    :return: The open archive.
    :rtype: zipfile.ZipFile
    :raises InvalidReleaseError: If it is not a zip file.
    """
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise InvalidReleaseError("Not a wheel: not a zip file") from error


def dist_info_folder(archive: zipfile.ZipFile) -> str:
    """
    The wheel's description folder, ``<name>-<version>.dist-info``.

    :param archive: The wheel.
    :type archive: zipfile.ZipFile
    :return: The folder's name.
    :rtype: str
    :raises InvalidReleaseError: Unless there is exactly one.
    """
    folders = {
        name.split("/")[0]
        for name in archive.namelist()
        if name.split("/")[0].endswith(DIST_INFO_SUFFIX)
    }
    if len(folders) != 1:
        raise InvalidReleaseError("A wheel has one .dist-info folder")
    return folders.pop()


def wheel_fields(archive: zipfile.ZipFile, file_name: str) -> Message:
    """
    Read one of the wheel's description files (``WHEEL``,
    ``METADATA``): lines of ``Key: value``, like e-mail headers.

    :param archive: The wheel.
    :type archive: zipfile.ZipFile
    :param file_name: File in the ``.dist-info`` folder.
    :type file_name: str
    :return: The fields.
    :rtype: Message
    :raises InvalidReleaseError: If the file is missing.
    """
    path = f"{dist_info_folder(archive)}/{file_name}"
    try:
        text = archive.read(path).decode("utf-8")
    except KeyError as error:
        raise InvalidReleaseError(f"The wheel has no {path}") from error
    return HeaderParser().parsestr(text)


def require_pure_python(wheel: Message) -> None:
    """
    Refuse a wheel built for one kind of machine: agents unzip it as
    it is, on any machine, with any Python 3.

    :param wheel: Fields of the ``WHEEL`` file.
    :type wheel: Message
    :raises InvalidReleaseError: If it is not pure Python.
    """
    pure = wheel.get("Root-Is-Purelib", "").strip().lower() == "true"
    if not pure or PURE_PYTHON_TAG not in wheel.get_all("Tag", []):
        raise InvalidReleaseError(
            f"A release must be pure Python ({PURE_PYTHON_TAG})"
        )


def safe_name(value: str) -> str:
    """
    Accept a name or version only if it can safely name a folder.

    :param value: Name or version from the wheel.
    :type value: str
    :return: The value, trimmed.
    :rtype: str
    :raises InvalidReleaseError: If it is empty or unsafe.
    """
    value = value.strip()
    if not SAFE_NAME.fullmatch(value):
        raise InvalidReleaseError(f"Unusable name or version: {value!r}")
    return value


def package_name(distribution: str) -> str:
    """
    The package a distribution installs, by the usual convention:
    ``af-scripts`` installs ``af_scripts``.

    :param distribution: Distribution name.
    :type distribution: str
    :return: Import name of its package.
    :rtype: str
    """
    return re.sub(r"[-.]+", "_", distribution).lower()


def read_catalog(archive: zipfile.ZipFile, package: str) -> CatalogDocument:
    """
    Read and check the catalog inside the package, building every
    task's parameter model as the server will (so a broken catalog is
    refused now, not at someone's submission).

    :param archive: The wheel.
    :type archive: zipfile.ZipFile
    :param package: The package holding the catalog.
    :type package: str
    :return: The catalog.
    :rtype: CatalogDocument
    :raises InvalidReleaseError: If it is missing or invalid.
    """
    path = f"{package}/{CATALOG_NAME}"
    try:
        document = CatalogDocument.model_validate_json(archive.read(path))
        Catalog(document)
    except KeyError as error:
        raise InvalidReleaseError(f"The wheel has no {path}") from error
    except (ValueError, TypeError) as error:
        raise InvalidReleaseError(f"{path} is invalid: {error}") from error
    return document


def module_files(module: str) -> set[str]:
    """
    Files that would make a module importable from the wheel.

    :param module: Dotted module name, e.g. ``afscripts.scripts.x``.
    :type module: str
    :return: ``a/b/x.py`` and ``a/b/x/__init__.py``.
    :rtype: set[str]
    """
    base = module.replace(".", "/")
    return {f"{base}.py", f"{base}/__init__.py"}


def require_modules(names: list[str], catalog: CatalogDocument) -> None:
    """
    Refuse a catalog naming a module the wheel does not contain.

    :param names: Every file in the wheel.
    :type names: list[str]
    :param catalog: Its catalog.
    :type catalog: CatalogDocument
    :raises InvalidReleaseError: If a task's module is missing.
    """
    present = set(names)
    missing = sorted(
        task.module
        for task in catalog.tasks
        if not module_files(task.module) & present
    )
    if missing:
        raise InvalidReleaseError(
            f"The catalog names modules the wheel lacks: {', '.join(missing)}"
        )
