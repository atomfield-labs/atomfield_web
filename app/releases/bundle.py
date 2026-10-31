"""
Read a release without running any of it.

What one publish uploads is a bundle, a zip file holding:

- ``release.json``: the name, the version, and which wheel is which;
- ``catalog.json``: the tasks, pipelines and workflows of this release;
- one wheel per package (workflow) and kind of machine.

A wheel is the zip file a Python package ships as. A job gets only its
own package's wheel, built for its agent's machine, so a lab never
receives a package it was not given. A release must:

- have a wheel for every package on every machine it names;
- hold, in each wheel, every module its package's tasks name;
- hold no source code, only compiled modules, so what reaches a server
  or a cluster cannot simply be read.
"""

import hashlib
import io
import itertools
import zipfile
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.catalog.catalog import Catalog
from app.catalog.models import (
    PACKAGE_NAME_PATTERN,
    WORKFLOW_ID_LENGTH,
    WORKFLOW_ID_PATTERN,
    CatalogDocument,
)
from app.core.machines import MACHINE_LENGTH

MANIFEST_NAME = "release.json"
CATALOG_NAME = "catalog.json"
# Every package on every machine, a few megabytes each.
MAX_RELEASE_BYTES = 100 * 1024 * 1024
TOO_BIG_MESSAGE = f"A release may be at most {MAX_RELEASE_BYTES} bytes"
SOURCE_SUFFIXES = (".py", ".pyi", ".pyx", ".pxd", ".c", ".cpp", ".h")
EMPTY_PACKAGE_MARKER = "/__init__.py"
COMPILED_SUFFIX = ".so"
SAFE_NAME = f"^{PACKAGE_NAME_PATTERN}$"
MACHINE_PATTERN = r"^[a-z0-9_-]+$"


class InvalidReleaseError(ValueError):
    """
    The file is not a release agents can run.
    """


class WheelEntry(BaseModel):
    """
    Which package and machine one wheel in the bundle is for.
    """

    package: str = Field(
        pattern=WORKFLOW_ID_PATTERN, max_length=WORKFLOW_ID_LENGTH
    )
    machine: str = Field(pattern=MACHINE_PATTERN, max_length=MACHINE_LENGTH)
    file: str


class BundleManifest(BaseModel):
    """
    The bundle's ``release.json``.
    """

    name: str = Field(pattern=SAFE_NAME)
    version: str = Field(pattern=SAFE_NAME)
    wheels: list[WheelEntry] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class WheelFile:
    """
    One checked wheel.

    :param package: The workflow it holds.
    :type package: str
    :param machine: The kind of machine it runs on.
    :type machine: str
    :param sha256: Its fingerprint, in hex.
    :type sha256: str
    :param data: The file.
    :type data: bytes
    """

    package: str
    machine: str
    sha256: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ReleaseContents:
    """
    What a valid release holds.

    :param name: Name, e.g. ``afscripts``.
    :type name: str
    :param version: Its version, e.g. ``0.2.0+g2e6d386``.
    :type version: str
    :param sha256: Fingerprint of the whole bundle, in hex.
    :type sha256: str
    :param catalog: The tasks it provides.
    :type catalog: CatalogDocument
    :param wheels: Its wheels.
    :type wheels: list[WheelFile]
    """

    name: str
    version: str
    sha256: str
    catalog: CatalogDocument
    wheels: list[WheelFile]


def read_release(data: bytes, may_hold_source: bool = False) -> ReleaseContents:
    """
    Check a bundle and read what it holds.

    :param data: The bundle.
    :type data: bytes
    :param may_hold_source: Accept readable code; for tests only.
    :type may_hold_source: bool
    :return: Its name, version, fingerprint, catalog and wheels.
    :rtype: ReleaseContents
    :raises InvalidReleaseError: If agents could not run it, or it holds
        source code.
    """
    if len(data) > MAX_RELEASE_BYTES:
        raise InvalidReleaseError(TOO_BIG_MESSAGE)
    bundle = open_zip(data)
    manifest = read_manifest(bundle)
    catalog = read_catalog(bundle)
    require_every_build(manifest, catalog)
    wheels = [
        read_wheel(bundle, entry, catalog, may_hold_source)
        for entry in manifest.wheels
    ]
    fingerprint = hashlib.sha256(data).hexdigest()
    return ReleaseContents(
        manifest.name, manifest.version, fingerprint, catalog, wheels
    )


def open_zip(data: bytes) -> zipfile.ZipFile:
    """
    Open bytes as the zip file they should be.

    :param data: The file.
    :type data: bytes
    :return: The open archive.
    :rtype: zipfile.ZipFile
    :raises InvalidReleaseError: If it is not a zip file.
    """
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise InvalidReleaseError("Not a release: not a zip file") from error


def read_member(bundle: zipfile.ZipFile, name: str) -> bytes:
    """
    One file of the bundle.

    :param bundle: The bundle.
    :type bundle: zipfile.ZipFile
    :param name: The file's name.
    :type name: str
    :return: Its bytes.
    :rtype: bytes
    :raises InvalidReleaseError: If it is missing.
    """
    try:
        return bundle.read(name)
    except KeyError as error:
        raise InvalidReleaseError(f"The release has no {name}") from error


def read_manifest(bundle: zipfile.ZipFile) -> BundleManifest:
    """
    Read ``release.json``.

    :param bundle: The bundle.
    :type bundle: zipfile.ZipFile
    :return: The manifest.
    :rtype: BundleManifest
    :raises InvalidReleaseError: If it is missing or invalid.
    """
    text = read_member(bundle, MANIFEST_NAME)
    try:
        return BundleManifest.model_validate_json(text)
    except ValidationError as error:
        message = f"{MANIFEST_NAME} is invalid: {error}"
        raise InvalidReleaseError(message) from error


def read_catalog(bundle: zipfile.ZipFile) -> CatalogDocument:
    """
    Read and check the catalog, building every task's parameter model
    as the server will (so a broken catalog is refused now, not at
    someone's submission).

    :param bundle: The bundle.
    :type bundle: zipfile.ZipFile
    :return: The catalog.
    :rtype: CatalogDocument
    :raises InvalidReleaseError: If it is missing or invalid.
    """
    text = read_member(bundle, CATALOG_NAME)
    try:
        document = CatalogDocument.model_validate_json(text)
        Catalog(document)
    except (ValueError, TypeError) as error:
        raise InvalidReleaseError(
            f"catalog.json is invalid: {error}"
        ) from error
    return document


def require_every_build(
    manifest: BundleManifest, catalog: CatalogDocument
) -> None:
    """
    Refuse a release missing a package on one of its machines, or with
    a wheel for a package its catalog does not have: a job could
    otherwise fail long after the publish.

    :param manifest: The manifest.
    :type manifest: BundleManifest
    :param catalog: The catalog.
    :type catalog: CatalogDocument
    :raises InvalidReleaseError: Naming what does not fit.
    """
    machines = {entry.machine for entry in manifest.wheels}
    packages = {workflow.id for workflow in catalog.workflows}
    given = {(entry.package, entry.machine) for entry in manifest.wheels}
    expected = set(itertools.product(packages, machines))
    if missing := sorted(expected - given):
        raise InvalidReleaseError(f"The release lacks wheels for: {missing}")
    if extra := sorted(given - expected):
        raise InvalidReleaseError(f"Wheels for no workflow: {extra}")


def read_wheel(
    bundle: zipfile.ZipFile,
    entry: WheelEntry,
    catalog: CatalogDocument,
    may_hold_source: bool,
) -> WheelFile:
    """
    Check one wheel of the bundle.

    :param bundle: The bundle.
    :type bundle: zipfile.ZipFile
    :param entry: Which wheel.
    :type entry: WheelEntry
    :param catalog: The catalog.
    :type catalog: CatalogDocument
    :param may_hold_source: Accept readable code; for tests only.
    :type may_hold_source: bool
    :return: The wheel.
    :rtype: WheelFile
    :raises InvalidReleaseError: If a module is missing, or it holds
        source code.
    """
    data = read_member(bundle, entry.file)
    wheel = open_zip(data)
    require_modules(wheel, entry.package, catalog)
    if not may_hold_source:
        require_no_source(wheel, entry.file)
    fingerprint = hashlib.sha256(data).hexdigest()
    return WheelFile(entry.package, entry.machine, fingerprint, data)


def module_present(module: str, names: set[str]) -> bool:
    """
    Whether a wheel's files make a module importable.

    :param module: Dotted module name, e.g. ``afscripts.scripts.x``.
    :type module: str
    :param names: Every file in the wheel.
    :type names: set[str]
    :return: True if it is there, compiled or as code.
    :rtype: bool
    """
    base = module.replace(".", "/")
    if {f"{base}.py", f"{base}{EMPTY_PACKAGE_MARKER}"} & names:
        return True
    return any(
        name.startswith(f"{base}.") and name.endswith(COMPILED_SUFFIX)
        for name in names
    )


def require_modules(
    wheel: zipfile.ZipFile, package: str, catalog: CatalogDocument
) -> None:
    """
    Refuse a wheel lacking a module its package's tasks name.

    :param wheel: The wheel.
    :type wheel: zipfile.ZipFile
    :param package: The workflow it holds.
    :type package: str
    :param catalog: The catalog.
    :type catalog: CatalogDocument
    :raises InvalidReleaseError: Naming the missing modules.
    """
    held = next(item.tasks for item in catalog.workflows if item.id == package)
    names = set(wheel.namelist())
    missing = sorted(
        task.module
        for task in catalog.tasks
        if task.id in held and not module_present(task.module, names)
    )
    if missing:
        raise InvalidReleaseError(
            f"The {package} wheel lacks: {', '.join(missing)}"
        )


def require_no_source(wheel: zipfile.ZipFile, name: str) -> None:
    """
    Refuse a wheel holding code anyone could read. An empty
    ``__init__.py`` only marks a folder as a package, so it may stay.

    :param wheel: The wheel.
    :type wheel: zipfile.ZipFile
    :param name: The wheel's file name, for the message.
    :type name: str
    :raises InvalidReleaseError: Naming the files.
    """
    readable = sorted(
        info.filename
        for info in wheel.infolist()
        if info.filename.endswith(SOURCE_SUFFIXES)
        and not (
            info.filename.endswith(EMPTY_PACKAGE_MARKER) and info.file_size == 0
        )
    )
    if readable:
        raise InvalidReleaseError(
            f"{name} holds source code: {', '.join(readable)}"
        )
