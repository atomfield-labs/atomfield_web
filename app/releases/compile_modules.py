"""
Compile a package's modules to machine code, beside their sources.

The publisher runs this file by itself in whatever environment a kind of
computer needs (see ``compiling``), so it imports nothing of AtomField::

    python compile_modules.py <folder holding the package>

No docstring or source line goes into a compiled file. One build works
on every Python from 3.11 on (the "limited API"), so a release needs one
wheel per kind of computer, not one per Python version.
"""

import os
import sys
from pathlib import Path

from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import Extension, setup

PACKAGE_MARKER = "__init__.py"
PYTHON_3_11 = "0x030B0000"
# Debug information holds names and paths nobody running a job needs.
NO_DEBUG_INFO = ["-g0"]
STRIP_SYMBOLS = {"darwin": ["-Wl,-x,-S"], "linux": ["-s"]}


def module_extension(path: Path) -> Extension:
    """
    How to compile one module.

    :param path: The module's file, from the folder holding the package.
    :type path: Path
    :return: The extension to build.
    :rtype: Extension
    """
    return Extension(
        ".".join(path.with_suffix("").parts),
        [str(path)],
        py_limited_api=True,
        define_macros=[
            ("Py_LIMITED_API", PYTHON_3_11),
            ("CYTHON_LIMITED_API", "1"),
        ],
        extra_compile_args=NO_DEBUG_INFO,
        extra_link_args=STRIP_SYMBOLS.get(sys.platform, []),
    )


def modules_in(folder: Path) -> list[Path]:
    """
    Every module under a folder, ``__init__.py`` files aside, as paths
    from the folder (which becomes the working directory).

    :param folder: The folder holding the package.
    :type folder: Path
    :return: The modules' files.
    :rtype: list[Path]
    """
    os.chdir(folder)
    paths = sorted(Path().rglob("*.py"))
    return [path for path in paths if path.name != PACKAGE_MARKER]


def compile_folder(folder: Path) -> None:
    """
    Compile every module under a folder, in place.

    :param folder: The folder holding the package.
    :type folder: Path
    """
    extensions = [module_extension(path) for path in modules_in(folder)]
    Options.docstrings = False
    Options.emit_code_comments = False
    directives = {
        "embedsignature": False,
        "binding": True,
        "annotation_typing": False,
    }
    sys.argv = ["setup", "build_ext", "--inplace"]
    setup(
        name="compiled",
        ext_modules=cythonize(
            extensions, language_level=3, compiler_directives=directives
        ),
    )


if __name__ == "__main__":
    compile_folder(Path(sys.argv[1]))
