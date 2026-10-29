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
"""

import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import agent.__main__  # noqa: F401  (loads the whole agent)
from app.core.cli import stops_cleanly

REPO_ROOT = Path(__file__).resolve().parents[1]
# Unpack beside the old copy, then swap: never half old, half new.
REMOTE_SCRIPT = (
    "set -e; mkdir -p ~/atomfield; cd ~/atomfield; "
    "rm -rf code.new; mkdir code.new; tar -xzf - -C code.new; "
    "rm -rf code; mv code.new code; find code -type f | wc -l"
)


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


def pack(files: list[str]) -> bytes:
    """
    The files as a gzipped tar archive, paths kept.

    :param files: Paths relative to the repository.
    :type files: list[str]
    :return: The archive.
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in files:
            archive.add(REPO_ROOT / name, arcname=name)
    return buffer.getvalue()


def ship(host: str) -> str:
    """
    Copy the agent to ``~/atomfield/code`` on a machine.

    :param host: What you type after ``ssh``.
    :type host: str
    :return: What was copied.
    :rtype: str
    :raises ShipError: If ssh or the unpacking failed.
    """
    files = loaded_files()
    done = subprocess.run(
        ["ssh", host, REMOTE_SCRIPT],
        input=pack(files),
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise ShipError(done.stderr.decode(errors="replace").strip())
    landed = done.stdout.decode().strip()
    return (
        f"Copied {len(files)} files; {host}:~/atomfield/code has {landed}.\n"
        "A running agent keeps its old copy until restarted there: "
        "python -m agent stop, then start."
    )


@stops_cleanly("Stopped. Run the same command again to copy the agent.")
def main(argv: list[str] | None = None) -> int:
    """
    Command line: copy, and say what happened.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(
        prog="python -m agent.ship",
        description="Copy the agent to ~/atomfield/code on a cluster.",
    )
    parser.add_argument("host", help="What you type after ssh")
    options = parser.parse_args(argv)
    try:
        print(ship(options.host))
    except ShipError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
