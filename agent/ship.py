"""
Copy the agent to a cluster, from the AtomField folder on your own
computer::

    uv run --python 3.11 python -m agent.ship mycluster

``mycluster`` is what you type after ``ssh`` (an address, or a
shortcut from ``~/.ssh/config``). Only the files the agent loads are
copied (its package and a few files of ``app``), found by loading the
agent and listing what it used, so no list of files can go stale. The
copy replaces ``~/atomfield/code`` on the cluster in one step, so
files from an older copy never linger; the agent's settings and work
folder live elsewhere and are not touched.

The copy also installs a shortcut, ``~/atomfield/agent``, that runs
the agent with its Python from any folder::

    ~/atomfield/agent start        (or login, stop, status)

Its Python is ``~/atomfield/env/bin/python`` unless ``--python`` names
another one.
"""

import argparse
import io
import subprocess
import sys
import tarfile
from collections.abc import Mapping
from pathlib import Path

import agent.__main__  # noqa: F401  (loads the whole agent)
from app.core.cli import stops_cleanly

REPO_ROOT = Path(__file__).resolve().parents[1]
# The shortcut travels inside the copy under this name, then moves to
# ~/atomfield/agent.
SHORTCUT_MEMBER = ".atomfield-shortcut"
DEFAULT_REMOTE_PYTHON = "~/atomfield/env/bin/python"
# Characters that would break out of the shortcut's quoted path.
UNSAFE_PATH_CHARACTERS = frozenset('"`\\')
# Unpack beside the old copy, then swap: never half old, half new.
REMOTE_SCRIPT = (
    "set -e; mkdir -p ~/atomfield; cd ~/atomfield; "
    "rm -rf code.new; mkdir code.new; tar -xzf - -C code.new; "
    "rm -rf code; mv code.new code; "
    f"mv code/{SHORTCUT_MEMBER} agent; chmod 755 agent; "
    "find code -type f | wc -l"
)
# -P keeps the folder you are in out of the import path, so the
# copied agent always runs, whatever folder you type the command in.
SHORTCUT_TEMPLATE = """\
#!/bin/sh
# The AtomField agent, copied here by agent.ship. From any folder:
#   ~/atomfield/agent login | start | stop | status
PYTHON="{python}"
if [ ! -x "$PYTHON" ]; then
  echo "No Python at $PYTHON: make the agent's environment first," >&2
  echo "or copy the agent again with --python <its python>." >&2
  exit 1
fi
PYTHONPATH="$HOME/atomfield/code${{PYTHONPATH:+:$PYTHONPATH}}"
ATOMFIELD_AGENT_COMMAND="$0"
export PYTHONPATH ATOMFIELD_AGENT_COMMAND
exec "$PYTHON" -P -m agent "$@"
"""


class ShipError(RuntimeError):
    """
    The copy did not reach the cluster.
    """


def loaded_files() -> list[str]:
    """
    The repository files this process has loaded: the agent's.

    :return: Paths relative to the repository, sorted.
    :rtype: list[str]
    """
    files = set()
    for module in list(sys.modules.values()):
        path = Path(getattr(module, "__file__", None) or "/").resolve()
        if path.is_relative_to(REPO_ROOT) and ".venv" not in path.parts:
            files.add(path.relative_to(REPO_ROOT).as_posix())
    return sorted(files)


def remote_path(path: str) -> str:
    """
    A path on the cluster as the shortcut writes it: a leading ``~/``
    becomes ``$HOME/``, which the cluster's shell expands.

    :param path: The path, as typed.
    :type path: str
    :return: The path for the shortcut.
    :rtype: str
    :raises ShipError: If it would break the shortcut's quotes.
    """
    if UNSAFE_PATH_CHARACTERS & set(path):
        raise ShipError(f"Not a usable path: {path}")
    return "$HOME/" + path[2:] if path.startswith("~/") else path


def shortcut_script(python: str) -> str:
    """
    The ``~/atomfield/agent`` shortcut: runs the copied agent with the
    given Python, passing on whatever follows it.

    :param python: The cluster's Python for the agent.
    :type python: str
    :return: The script.
    :rtype: str
    """
    return SHORTCUT_TEMPLATE.format(python=remote_path(python))


def pack(files: list[str], generated: Mapping[str, str]) -> bytes:
    """
    The files as a gzipped tar archive, paths kept, with generated
    executable files added.

    :param files: Paths relative to the repository.
    :type files: list[str]
    :param generated: Name in the archive -> text.
    :type generated: Mapping[str, str]
    :return: The archive.
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in files:
            archive.add(REPO_ROOT / name, arcname=name)
        for name, text in generated.items():
            data = text.encode()
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o755
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def ship(host: str, python: str = DEFAULT_REMOTE_PYTHON) -> str:
    """
    Copy the agent to ``~/atomfield/code`` on a machine, and install
    its shortcut.

    :param host: What you type after ``ssh``.
    :type host: str
    :param python: The cluster's Python for the agent.
    :type python: str
    :return: What was copied, and how to use it.
    :rtype: str
    :raises ShipError: If ssh or the unpacking failed.
    """
    files = loaded_files()
    shortcut = {SHORTCUT_MEMBER: shortcut_script(python)}
    done = subprocess.run(
        ["ssh", host, REMOTE_SCRIPT],
        input=pack(files, shortcut),
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise ShipError(done.stderr.decode(errors="replace").strip())
    landed = done.stdout.decode().strip()
    return shipped(host, len(files), landed)


def shipped(host: str, copied: int, landed: str) -> str:
    """
    What a finished copy tells the person.

    :param host: Where it went.
    :type host: str
    :param copied: Files sent.
    :type copied: int
    :param landed: Files the cluster counted in its copy.
    :type landed: str
    :return: A few lines.
    :rtype: str
    """
    return (
        f"Copied {copied} files; {host}:~/atomfield/code has {landed}.\n"
        "On the cluster, from any folder: ~/atomfield/agent start (or "
        "login, stop, status).\nA running agent keeps its old copy until "
        "you stop and start it."
    )


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line.

    :return: Parser for ``python -m agent.ship``.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python -m agent.ship",
        description="Copy the agent to ~/atomfield/code on a cluster.",
    )
    parser.add_argument("host", help="What you type after ssh")
    parser.add_argument(
        "--python",
        default=DEFAULT_REMOTE_PYTHON,
        help="The cluster's Python for the agent "
        f"(default: {DEFAULT_REMOTE_PYTHON})",
    )
    return parser


@stops_cleanly("Stopped. Run the same command again to copy the agent.")
def main(argv: list[str] | None = None) -> int:
    """
    Command line: copy, and say what happened.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    try:
        print(ship(options.host, options.python))
    except ShipError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
