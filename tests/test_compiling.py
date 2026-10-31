"""
Turning a commit of the scripts into a compiled release bundle: which
modules each package needs, what a wheel may hold, and a bundle the
server would take. One test compiles for real; it needs uv, a C
compiler and, the first time, the network, so it runs only with
``pytest -m compiler``.
"""

import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.catalog.argv import RUN_MAIN
from app.catalog.models import CatalogDocument
from app.releases.bundle import read_release
from app.releases.compiling import (
    COMPILER,
    LINUX,
    LINUX_IMAGE,
    MAC,
    MACHINES,
    build_command,
    check_bundle,
    compiled_file,
    module_files,
    modules_by_workflow,
    native_build,
    pack_bundle,
    parse_catalog,
    wheel_members,
    wheels_for,
    zip_bytes,
)
from app.releases.tools import PublishError, run_tool
from tests.fake_release import FIXTURE_CATALOG

# A fake package shaped like the fixture catalog's two packages: a
# chain with a helper they share, a package of its own, a data table
# the helper names, one it does not, and the catalog tools.
SOURCE = {
    "toy/__init__.py": "VALUE = 1\n",
    "toy/opt_driver.py": "from toy.helpers import shared\n",
    "toy/network_driver.py": "from toy import helpers\n",
    "toy/helpers.py": "TABLE = 'values.toml'\nshared = 1\n",
    "toy/values.toml": "a = 1\n",
    "toy/unused.toml": "b = 2\n",
    "toy/solo_driver.py": "import toy.other_helper\n",
    "toy/other_helper.py": "",
    "toy/catalog/__init__.py": "",
    "toy/catalog/export.py": "",
}
CHAIN = {"toy.opt_driver", "toy.network_driver", "toy.helpers"}
SOLO = {"toy.solo_driver", "toy.other_helper"}
CHAIN_WHEEL = [
    "toy/__init__.py",
    "toy/helpers.abi3.so",
    "toy/network_driver.abi3.so",
    "toy/opt_driver.abi3.so",
    "toy/values.toml",
]
SOLO_WHEEL = [
    "toy/__init__.py",
    "toy/other_helper.abi3.so",
    "toy/solo_driver.abi3.so",
]
COMPILED = b"machine code"
ELSEWHERE = "freebsd-riscv64"


def write_files(root: Path, files: dict[str, str]) -> Path:
    """
    Write files under a folder, making the folders they need.

    :param root: The folder.
    :type root: Path
    :param files: Path -> text.
    :type files: dict[str, str]
    :return: The folder.
    :rtype: Path
    """
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def toy_catalog() -> CatalogDocument:
    """
    The fixture catalog: two packages, one task of its own.

    :return: The catalog.
    :rtype: CatalogDocument
    """
    return CatalogDocument.model_validate_json(FIXTURE_CATALOG.read_text())


def pretend_compiled(root: Path, modules: set[str]) -> Path:
    """
    Fake a compiler's work: beside each module's source, a compiled
    file and the leftovers a build makes (the C file, a build folder).

    :param root: The folder holding the package.
    :type root: Path
    :param modules: Dotted module names.
    :type modules: set[str]
    :return: The folder.
    :rtype: Path
    """
    for module in modules:
        path = root.joinpath(*module.split("."))
        path.with_name(f"{path.name}.abi3.so").write_bytes(COMPILED)
        path.with_name(f"{path.name}.c").write_text("/* generated */\n")
    write_files(root, {"build/temp/leftover.o": "object"})
    return root


def test_a_package_needs_only_what_its_tasks_import(tmp_path: Path):
    """
    Each package gets its tasks' modules and what they import, however
    indirectly, and nothing of the other.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    source = write_files(tmp_path, SOURCE)
    files = module_files(source, "toy")
    needs = modules_by_workflow(toy_catalog(), files)
    assert needs == {"toy_chain": CHAIN, "toy_other": SOLO}


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        ({"toy/solo_driver.py": "import toy.catalog.export\n"}, "never ship"),
        ({"toy/solo_driver.py": "from . import other_helper\n"}, "absolute"),
        ({"toy/solo_driver.py": None}, "not here"),
    ],
    ids=["catalog-tools", "relative-import", "missing-module"],
)
def test_what_cannot_ship_stops_the_build(
    tmp_path: Path, change: dict[str, str | None], complaint: str
):
    """
    A task needing the catalog tools, an import that cannot be followed
    with certainty, or a module that is not there: all stop the build,
    naming the problem.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param change: A file of the fake package changed (None removes it).
    :type change: dict[str, str | None]
    :param complaint: Part of the expected message.
    :type complaint: str
    """
    files = {**SOURCE, **change}
    present = {name: text for name, text in files.items() if text is not None}
    source = write_files(tmp_path, present)
    with pytest.raises(PublishError, match=complaint):
        modules_by_workflow(toy_catalog(), module_files(source, "toy"))


def test_a_commit_without_workflows_has_nothing_to_ship():
    """
    The packages are the workflows: a catalog without any cannot be
    published.
    """
    document = json.loads(FIXTURE_CATALOG.read_text())
    del document["workflows"]
    with pytest.raises(PublishError, match="no workflows"):
        parse_catalog(json.dumps(document))
    with pytest.raises(PublishError, match="is invalid"):
        parse_catalog("{}")


def test_a_wheel_holds_only_what_is_picked_by_name(tmp_path: Path):
    """
    Compiled files, the data tables the modules name, and an empty
    ``__init__.py`` per folder: not the sources, the generated C, the
    build leftovers, a table nobody names, or the package's own
    ``__init__.py`` with its code.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    built = pretend_compiled(write_files(tmp_path, SOURCE), CHAIN | SOLO)
    members = wheel_members(built, CHAIN)
    assert sorted(members) == CHAIN_WHEEL
    assert members["toy/__init__.py"] == b""
    assert members["toy/helpers.abi3.so"] == COMPILED
    assert members["toy/values.toml"] == b"a = 1\n"


def test_each_package_gets_its_own_files_only(tmp_path: Path):
    """
    The package of its own gets none of the chain's files, tables
    included: what a lab is not given never reaches it.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    built = pretend_compiled(write_files(tmp_path, SOURCE), CHAIN | SOLO)
    assert sorted(wheel_members(built, SOLO)) == SOLO_WHEEL


def test_a_module_that_did_not_compile_is_named(tmp_path: Path):
    """
    A needed module with no compiled file stops the build, rather than
    shipping a wheel that fails at someone's first job.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    built = write_files(tmp_path, SOURCE)
    pretend_compiled(built, {"toy.opt_driver"})
    with pytest.raises(PublishError, match="toy.helpers did not compile"):
        wheel_members(built, {"toy.opt_driver", "toy.helpers"})
    assert compiled_file(built, "toy.opt_driver").name == "opt_driver.abi3.so"


def test_a_zip_is_the_same_bytes_every_time():
    """
    The same files make the same zip whatever order they come in, so
    packing again changes nothing.
    """
    forward = {"b.txt": "two", "a.txt": b"one"}
    backward = {"a.txt": b"one", "b.txt": "two"}
    assert zip_bytes(forward) == zip_bytes(backward)
    with zipfile.ZipFile(io.BytesIO(zip_bytes(forward))) as archive:
        assert archive.namelist() == ["a.txt", "b.txt"]


def fake_bundle(
    tmp_path: Path,
    machines: tuple[str, ...],
    extra: dict[str, bytes] | None = None,
) -> bytes:
    """
    A bundle of the fake package, built from placeholders for the
    compiled files.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param machines: The kinds of computer it is for.
    :type machines: tuple[str, ...]
    :param extra: Files added to every wheel (path -> bytes).
    :type extra: dict[str, bytes] | None
    :return: The bundle.
    :rtype: bytes
    """
    built = write_files(tmp_path, SOURCE)
    pretend_compiled(built, CHAIN | SOLO)
    needs = {"toy_chain": CHAIN, "toy_other": SOLO}
    wheels = {}
    for machine in machines:
        wheels |= wheels_for(machine, built, needs)
    if extra:
        wheels = {
            key: zip_bytes({**read_wheel(data), **extra})
            for key, data in wheels.items()
        }
    return pack_bundle("toy", "1.0.0", FIXTURE_CATALOG.read_text(), wheels)


def read_wheel(data: bytes) -> dict[str, bytes]:
    """
    The files of a wheel.

    :param data: The wheel.
    :type data: bytes
    :return: Path -> content.
    :rtype: dict[str, bytes]
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_a_bundle_holds_a_wheel_per_package_and_machine(tmp_path: Path):
    """
    The bundle passes the server's own checks, with no allowance for
    source, and names which wheel is which.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    bundle = fake_bundle(tmp_path, (MAC, LINUX))
    check_bundle(bundle)
    contents = read_release(bundle)
    assert (contents.name, contents.version) == ("toy", "1.0.0")
    assert {(wheel.package, wheel.machine) for wheel in contents.wheels} == {
        ("toy_chain", MAC),
        ("toy_chain", LINUX),
        ("toy_other", MAC),
        ("toy_other", LINUX),
    }


def test_a_bundle_carrying_source_is_never_sent(tmp_path: Path):
    """
    Even if the packing went wrong, the publisher's own check stops
    readable code before it leaves.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    leaky = fake_bundle(tmp_path, (LINUX,), {"toy/helpers.py": b"x = 1\n"})
    with pytest.raises(PublishError, match="holds source code"):
        check_bundle(leaky)


def test_the_commands_that_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Linux is built in the oldest Linux we support, whatever computer
    publishes; this computer's kind is built here; any other kind
    cannot be built.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param monkeypatch: Makes this computer a Mac.
    :type monkeypatch: pytest.MonkeyPatch
    """
    linux = build_command(LINUX, tmp_path)
    assert linux[:2] == ["docker", "run"]
    assert LINUX_IMAGE in linux
    assert f"{tmp_path.resolve()}:/io" in linux
    assert "chown -R" in linux[-1]
    monkeypatch.setattr("app.releases.compiling.this_machine", lambda: MAC)
    assert build_command(MAC, tmp_path)[:2] == ["uv", "run"]
    with pytest.raises(PublishError, match="can build for"):
        build_command(ELSEWHERE, tmp_path)
    assert set(MACHINES) == {MAC, LINUX}


GREETER = '''"""SECRET-MODULE-DOCSTRING"""


def hello():
    """SECRET-FUNCTION-DOCSTRING"""
    # SECRET-COMMENT
    return "hi " + "there"


def main():
    print(hello())
'''


def compile_greeter(work: Path) -> Path:
    """
    Compile a one-module package here, for real.

    :param work: Empty folder to work in.
    :type work: Path
    :return: The folder holding the compiled package.
    :rtype: Path
    """
    files = {"toy/__init__.py": "", "toy/greeter.py": GREETER}
    source = write_files(work / "src", files)
    shutil.copy(COMPILER, work)
    run_tool(native_build(work))
    return source


@pytest.mark.compiler
def test_a_module_is_compiled_and_runs_without_its_source(tmp_path: Path):
    """
    The real compiler: afterwards the module starts the way a job
    starts it, its source and the generated C removed, and neither its
    docstrings nor its comments are in the compiled file.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    source = compile_greeter(tmp_path)
    compiled = compiled_file(source, "toy.greeter")
    for leftover in ("toy/greeter.py", "toy/greeter.c"):
        (source / leftover).unlink()
    start = [sys.executable, "-u", "-c", RUN_MAIN.format(module="toy.greeter")]
    env = {"PYTHONPATH": str(source)}
    done = subprocess.run(
        start, env=env, capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout.strip()) == (0, "hi there")
    for secret in (b"SECRET-MODULE", b"SECRET-FUNCTION", b"SECRET-COMMENT"):
        assert secret not in compiled.read_bytes()
