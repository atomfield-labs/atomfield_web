"""
Turn one exported commit of the scripts into a release bundle, compiled,
so no readable code leaves the computer publishing it:

1. follow the imports from each package's tasks, to see which modules
   the package needs;
2. compile every module once per kind of computer (``compile_modules``);
3. pack one zip per package and machine holding only compiled modules,
   empty ``__init__.py`` files and data tables;
4. put those and the catalog in one bundle, and check it exactly as the
   server will.

A wheel's files are picked by name rather than leaving the unwanted
ones out, so source cannot slip in beside the compiled modules.
"""

import ast
import io
import json
import os
import re
import shutil
import tomllib
import zipfile
from collections.abc import Collection, Iterable
from pathlib import Path

from app.catalog.models import CatalogDocument
from app.core.machines import this_machine
from app.releases.bundle import (
    CATALOG_NAME,
    MANIFEST_NAME,
    InvalidReleaseError,
    read_release,
)
from app.releases.tools import PublishError, run_tool

LINUX = "linux-x86_64"
MAC = "darwin-arm64"
MACHINES = (MAC, LINUX)
# The oldest Linux in use (glibc 2.17): what is built
# there runs on every newer one.
LINUX_IMAGE = "quay.io/pypa/manylinux2014_x86_64"
LINUX_PLATFORM = "linux/amd64"
LINUX_PYTHON = "/opt/python/cp311-cp311/bin/python"
# Cython 3.1 is the first with the limited API, one build for every
# Python from 3.11.
BUILD_TOOLS = ("cython>=3.1,<4", "setuptools")
COMPILER = Path(__file__).with_name("compile_modules.py")
SOURCE_FOLDER = "src"
# The exporter and the ready-made pipelines: never needed to run a job,
# and they hold the catalog's sources.
CATALOG_TOOLS = "catalog"
PACKAGE_MARKER = "__init__.py"
COMPILED_SUFFIX = ".abi3.so"
DATA_SUFFIX = ".toml"
SHORT_COMMIT = 7
# Fixed timestamps: the same files always make the same bytes.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def package_name(distribution: str) -> str:
    """
    The package a distribution installs: ``af-scripts`` installs
    ``af_scripts``.

    :param distribution: Distribution name.
    :type distribution: str
    :return: Import name of its package.
    :rtype: str
    """
    return re.sub(r"[-.]+", "_", distribution).lower()


def project_name(tree: Path) -> str:
    """
    The distribution name in ``pyproject.toml``.

    :param tree: The exported commit.
    :type tree: Path
    :return: e.g. ``afscripts``.
    :rtype: str
    """
    with (tree / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["name"]


def labelled_version(tree: Path, commit: str) -> str:
    """
    The version a commit is published under: the project's, plus the
    commit, so every commit is its own release with no version to bump
    by hand, and the version says where it came from.

    :param tree: The exported commit.
    :type tree: Path
    :param commit: The commit.
    :type commit: str
    :return: e.g. ``0.1.0+g2e6d386``.
    :rtype: str
    """
    with (tree / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    return f"{version}+g{commit[:SHORT_COMMIT]}"


def read_catalog(tree: Path) -> str:
    """
    The commit's catalog, as text.

    :param tree: The exported commit.
    :type tree: Path
    :return: The file's contents.
    :rtype: str
    :raises PublishError: If the commit has none.
    """
    path = tree / CATALOG_NAME
    if not path.is_file():
        raise PublishError(f"This commit has no {CATALOG_NAME}")
    return path.read_text(encoding="utf-8")


def parse_catalog(text: str) -> CatalogDocument:
    """
    Check the catalog as the server will.

    :param text: The catalog's JSON.
    :type text: str
    :return: The catalog.
    :rtype: CatalogDocument
    :raises PublishError: If it is invalid, or has no workflows: the
        packages are the workflows, so there would be nothing to ship.
    """
    try:
        catalog = CatalogDocument.model_validate_json(text)
    except ValueError as error:
        raise PublishError(f"{CATALOG_NAME} is invalid: {error}") from error
    if not catalog.workflows:
        raise PublishError(f"{CATALOG_NAME} has no workflows to ship")
    return catalog


def module_files(source: Path, package: str) -> dict[str, Path]:
    """
    Every module of the package, ``__init__.py`` files aside.

    :param source: The folder holding the package.
    :type source: Path
    :param package: The package's name.
    :type package: str
    :return: Dotted module name -> its file.
    :rtype: dict[str, Path]
    """
    found = {}
    for path in sorted((source / package).rglob("*.py")):
        if path.name != PACKAGE_MARKER:
            parts = path.relative_to(source).with_suffix("").parts
            found[".".join(parts)] = path
    return found


def from_import_names(path: Path, node: ast.ImportFrom) -> set[str]:
    """
    What a ``from x import y`` line may be importing: ``x``, and each
    ``x.y`` (which is a module when ``y`` is one).

    :param path: The module the line is in, for the message.
    :type path: Path
    :param node: The line.
    :type node: ast.ImportFrom
    :return: Dotted names.
    :rtype: set[str]
    :raises PublishError: For a relative import, which could not be
        followed with certainty.
    """
    if node.level or node.module is None:
        raise PublishError(f"{path}: use absolute imports")
    names = {f"{node.module}.{item.name}" for item in node.names}
    return {node.module, *names}


def imports_of(path: Path, known: Collection[str]) -> set[str]:
    """
    The package's modules one module imports, anywhere in its code.

    :param path: The module's file.
    :type path: Path
    :param known: Every module of the package.
    :type known: Collection[str]
    :return: The modules it imports.
    :rtype: set[str]
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= from_import_names(path, node)
    return names & set(known)


def require_shippable(module: str, files: dict[str, Path]) -> None:
    """
    Refuse a module that is missing, or that never ships.

    :param module: Dotted module name.
    :type module: str
    :param files: Every module of the package, by name.
    :type files: dict[str, Path]
    :raises PublishError: Naming the module.
    """
    if module not in files:
        raise PublishError(f"A task needs {module}, which is not here")
    if module.split(".")[1] == CATALOG_TOOLS:
        raise PublishError(
            f"A task needs {module}, but the catalog tools never ship"
        )


def needed_modules(roots: Iterable[str], files: dict[str, Path]) -> set[str]:
    """
    Some modules and everything they import, however indirectly.

    :param roots: The modules to start from.
    :type roots: Iterable[str]
    :param files: Every module of the package, by name.
    :type files: dict[str, Path]
    :return: The modules needed.
    :rtype: set[str]
    :raises PublishError: If one is missing or never ships.
    """
    waiting = list(roots)
    needed: set[str] = set()
    while waiting:
        module = waiting.pop()
        if module not in needed:
            require_shippable(module, files)
            needed.add(module)
            waiting += imports_of(files[module], files)
    return needed


def modules_by_workflow(
    catalog: CatalogDocument, files: dict[str, Path]
) -> dict[str, set[str]]:
    """
    What each package needs, from the modules of its tasks.

    :param catalog: The commit's catalog.
    :type catalog: CatalogDocument
    :param files: Every module of the package, by name.
    :type files: dict[str, Path]
    :return: Workflow id -> the modules its wheel must hold.
    :rtype: dict[str, set[str]]
    """
    module_of = {task.id: task.module for task in catalog.tasks}
    return {
        workflow.id: needed_modules(
            (module_of[task] for task in workflow.tasks), files
        )
        for workflow in catalog.workflows
    }


def linux_steps() -> str:
    """
    What the Linux container runs: install the build tools, compile,
    and hand every file back to the person publishing. What the
    container makes belongs to root, so this happens even after a
    failure: the scratch folder must stay removable.

    :return: A shell command line.
    :rtype: str
    """
    tools = " ".join(f"'{tool}'" for tool in BUILD_TOOLS)
    install = f"{LINUX_PYTHON} -m pip install --quiet {tools}"
    compile_all = f"{LINUX_PYTHON} /io/{COMPILER.name} /io/{SOURCE_FOLDER}"
    owner = f"{os.getuid()}:{os.getgid()}"
    handback = f"status=$?; chown -R {owner} /io; exit $status"
    return f"{install} && {compile_all}; {handback}"


def linux_build(folder: Path) -> list[str]:
    """
    The command compiling for Linux, in the oldest Linux we support.

    :param folder: Holds the compiler and the ``src`` folder.
    :type folder: Path
    :return: The command.
    :rtype: list[str]
    """
    run = ["docker", "run", "--rm", "--platform", LINUX_PLATFORM]
    mount = f"{folder.resolve()}:/io"
    return [*run, "-v", mount, LINUX_IMAGE, "sh", "-c", linux_steps()]


def native_build(folder: Path) -> list[str]:
    """
    The command compiling for this very computer.

    :param folder: Holds the compiler and the ``src`` folder.
    :type folder: Path
    :return: The command.
    :rtype: list[str]
    """
    tools = [item for tool in BUILD_TOOLS for item in ("--with", tool)]
    uv_run = ["uv", "run", "--no-project", "--python", "3.11", *tools]
    compiler = (folder / COMPILER.name).resolve()
    return [
        *uv_run,
        "python",
        str(compiler),
        str((folder / SOURCE_FOLDER).resolve()),
    ]


def build_command(machine: str, folder: Path) -> list[str]:
    """
    The command compiling for a kind of computer.

    :param machine: The kind of computer.
    :type machine: str
    :param folder: Holds the compiler and the ``src`` folder.
    :type folder: Path
    :return: The command.
    :rtype: list[str]
    :raises PublishError: If this computer cannot build for it.
    """
    if machine == LINUX:
        return linux_build(folder)
    if machine != this_machine():
        raise PublishError(f"Only a {machine} computer can build for {machine}")
    return native_build(folder)


def compile_for(machine: str, source: Path, scratch: Path) -> Path:
    """
    Compile a copy of the package for one kind of computer.

    :param machine: The kind of computer.
    :type machine: str
    :param source: The folder holding the package.
    :type source: Path
    :param scratch: A folder to work in.
    :type scratch: Path
    :return: The folder holding the compiled package.
    :rtype: Path
    :raises PublishError: If it does not compile.
    """
    folder = scratch / machine
    built = folder / SOURCE_FOLDER
    shutil.copytree(source, built, ignore=shutil.ignore_patterns(CATALOG_TOOLS))
    shutil.copy(COMPILER, folder)
    run_tool(build_command(machine, folder))
    return built


def compiled_file(built: Path, module: str) -> Path:
    """
    A module's compiled file.

    :param built: The folder holding the compiled package.
    :type built: Path
    :param module: Dotted module name.
    :type module: str
    :return: Its file.
    :rtype: Path
    :raises PublishError: If it was not compiled.
    """
    path = built.joinpath(*module.split("."))
    compiled = path.with_name(f"{path.name}{COMPILED_SUFFIX}")
    if not compiled.is_file():
        raise PublishError(f"{module} did not compile")
    return compiled


def package_markers(module: str) -> list[str]:
    """
    The empty ``__init__.py`` files that make a module's folders
    packages.

    :param module: Dotted module name.
    :type module: str
    :return: Their paths in a wheel.
    :rtype: list[str]
    """
    folders = module.split(".")[:-1]
    return [
        "/".join([*folders[: depth + 1], PACKAGE_MARKER])
        for depth in range(len(folders))
    ]


def tables_named_by(source: Path) -> list[Path]:
    """
    The data tables a module names in its code: a string that is the
    name of a ``.toml`` file beside it. Only those ship with it, so a
    package never carries another's tables.

    :param source: The module's source file.
    :type source: Path
    :return: The tables' files.
    :rtype: list[Path]
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(DATA_SUFFIX)
        and Path(node.value).name == node.value
    }
    beside = (source.parent / name for name in sorted(names))
    return [path for path in beside if path.is_file()]


def module_members(built: Path, module: str) -> dict[str, bytes]:
    """
    What one module puts in a wheel: its compiled file, and the data
    tables it names.

    :param built: The folder holding the compiled package.
    :type built: Path
    :param module: Dotted module name.
    :type module: str
    :return: Path in the wheel -> content.
    :rtype: dict[str, bytes]
    """
    compiled = compiled_file(built, module)
    source = compiled.with_name(f"{module.split('.')[-1]}.py")
    return {
        path.relative_to(built).as_posix(): path.read_bytes()
        for path in [compiled, *tables_named_by(source)]
    }


def wheel_members(built: Path, modules: Iterable[str]) -> dict[str, bytes]:
    """
    What a wheel holds, picked by name: the modules' compiled files,
    the data tables they name, and an empty ``__init__.py`` per folder.

    :param built: The folder holding the compiled package.
    :type built: Path
    :param modules: The modules it needs.
    :type modules: Iterable[str]
    :return: Path in the wheel -> content.
    :rtype: dict[str, bytes]
    """
    members: dict[str, bytes] = {}
    for module in modules:
        members |= module_members(built, module)
        members |= dict.fromkeys(package_markers(module), b"")
    return members


def zip_bytes(members: dict[str, bytes | str]) -> bytes:
    """
    A zip file holding these files, the same bytes every time.

    :param members: Path -> content.
    :type members: dict[str, bytes | str]
    :return: The zip's bytes.
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in sorted(members.items()):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            archive.writestr(info, content, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def wheels_for(
    machine: str, built: Path, needs: dict[str, set[str]]
) -> dict[tuple[str, str], bytes]:
    """
    One wheel per package, from one machine's compiled modules.

    :param machine: The kind of computer.
    :type machine: str
    :param built: The folder holding the compiled package.
    :type built: Path
    :param needs: Workflow id -> the modules its wheel must hold.
    :type needs: dict[str, set[str]]
    :return: (workflow id, machine) -> the wheel's bytes.
    :rtype: dict[tuple[str, str], bytes]
    """
    return {
        (package, machine): zip_bytes(wheel_members(built, modules))
        for package, modules in needs.items()
    }


def pack_bundle(
    name: str,
    version: str,
    catalog_text: str,
    wheels: dict[tuple[str, str], bytes],
) -> bytes:
    """
    Put the catalog and the wheels in one file, with a manifest saying
    which wheel is which.

    :param name: The release's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :param catalog_text: The catalog's JSON.
    :type catalog_text: str
    :param wheels: (workflow id, machine) -> the wheel's bytes.
    :type wheels: dict[tuple[str, str], bytes]
    :return: The bundle's bytes.
    :rtype: bytes
    """
    files = {
        f"{pack}-{machine}.whl": data
        for (pack, machine), data in wheels.items()
    }
    entries = [
        {"package": pack, "machine": machine, "file": f"{pack}-{machine}.whl"}
        for pack, machine in wheels
    ]
    manifest = {"name": name, "version": version, "wheels": entries}
    manifest_text = json.dumps(manifest, indent=2)
    return zip_bytes(
        {MANIFEST_NAME: manifest_text, CATALOG_NAME: catalog_text, **files}
    )


def check_bundle(bundle: bytes) -> None:
    """
    Check a bundle as the server will, before it is sent: the same
    rules, with no allowance for source code.

    :param bundle: The bundle.
    :type bundle: bytes
    :raises PublishError: If the server would refuse it.
    """
    try:
        read_release(bundle)
    except InvalidReleaseError as error:
        raise PublishError(f"The server would refuse it: {error}") from error


def build_bundle(
    tree: Path,
    version: str,
    scratch: Path,
    machines: Collection[str] = MACHINES,
) -> bytes:
    """
    Compile an exported commit and bundle it.

    :param tree: The exported commit.
    :type tree: Path
    :param version: The version it is published under.
    :type version: str
    :param scratch: A folder to compile in.
    :type scratch: Path
    :param machines: The kinds of computer to build for.
    :type machines: Collection[str]
    :return: The bundle's bytes.
    :rtype: bytes
    :raises PublishError: If anything cannot be built or checked.
    """
    catalog_text = read_catalog(tree)
    catalog = parse_catalog(catalog_text)
    name = project_name(tree)
    source = tree / SOURCE_FOLDER
    files = module_files(source, package_name(name))
    needs = modules_by_workflow(catalog, files)
    wheels: dict[tuple[str, str], bytes] = {}
    for machine in machines:
        built = compile_for(machine, source, scratch)
        wheels |= wheels_for(machine, built, needs)
    bundle = pack_bundle(name, version, catalog_text, wheels)
    check_bundle(bundle)
    return bundle
