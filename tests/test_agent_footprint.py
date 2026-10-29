"""
What a cluster gets: ``python -m agent.ship`` copies the files the
agent loads, which are its package and a few small files of app (the
job contract, the catalog models, how commands end), and nothing of
the server (FastAPI, SQLAlchemy, Redis). Both tests run the agent in a
fresh interpreter, as on a cluster.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_FILES = {
    "app/__init__.py",
    "app/agents/__init__.py",
    "app/agents/schemas.py",
    "app/catalog/__init__.py",
    "app/catalog/argv.py",
    "app/catalog/models.py",
    "app/core/__init__.py",
    "app/core/cli.py",
}
SERVER_PACKAGES = {"alembic", "asyncpg", "fastapi", "redis", "sqlalchemy"}
PROBE = """
import json, sys
from agent.ship import loaded_files
packages = sorted({name.split(".")[0] for name in sys.modules})
print(json.dumps({"files": loaded_files(), "packages": packages}))
"""
# Stands in for ssh: runs the remote command here, in $HOME.
FAKE_SSH = '#!/bin/sh\nshift\nexec sh -c "$1"\n'


def run_python(arguments: list[str], env: dict | None = None):
    """
    Run Python from the repository folder, as ``uv run`` would.

    :param arguments: Arguments after ``python``.
    :type arguments: list[str]
    :param env: Environment; this process's by default.
    :type env: dict | None
    :return: The finished process.
    :rtype: subprocess.CompletedProcess
    """
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_the_agent_needs_only_its_package_and_a_few_app_files():
    """
    Outside ``agent/``, the agent loads exactly these files of app, and
    no server package at all.
    """
    loaded = json.loads(run_python(["-c", PROBE]).stdout)
    files = loaded["files"]
    outside = {name for name in files if not name.startswith("agent/")}

    assert outside == APP_FILES
    assert not SERVER_PACKAGES & set(loaded["packages"])


def cluster_environment(tmp_path: Path) -> dict:
    """
    An environment whose ``ssh`` runs the remote command here, with a
    home folder of its own (the "cluster").

    :param tmp_path: Empty directory for the test.
    :type tmp_path: Path
    :return: Environment variables.
    :rtype: dict
    """
    fake = tmp_path / "bin" / "ssh"
    fake.parent.mkdir()
    fake.write_text(FAKE_SSH)
    fake.chmod(0o755)
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
    }
    environment.pop("PYTHONPATH", None)
    return environment


def run_shortcut(tmp_path: Path, env: dict, *arguments: str):
    """
    Run ``~/atomfield/agent`` from a folder outside the repository.

    :param tmp_path: The test's directory (the "cluster").
    :type tmp_path: Path
    :param env: The cluster's environment.
    :type env: dict
    :param arguments: What follows the shortcut.
    :type arguments: str
    :return: The finished process.
    :rtype: subprocess.CompletedProcess
    """
    shortcut = tmp_path / "home" / "atomfield" / "agent"
    return subprocess.run(
        [str(shortcut), *arguments],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ship_copies_the_agent_and_replaces_the_old_copy(tmp_path: Path):
    """
    Through a fake ssh, ``~/atomfield/code`` ends up holding exactly
    the agent's files; a file from an older copy is gone; the shortcut
    sits beside it, ready to run.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    env = cluster_environment(tmp_path)
    code = tmp_path / "home" / "atomfield" / "code"
    code.mkdir(parents=True)
    (code / "stale.py").write_text("old copy")

    message = run_python(["-m", "agent.ship", "mycluster"], env).stdout
    expected = json.loads(run_python(["-c", PROBE]).stdout)["files"]
    copied = sorted(
        path.relative_to(code).as_posix()
        for path in code.rglob("*")
        if path.is_file()
    )
    shortcut = tmp_path / "home" / "atomfield" / "agent"
    assert copied == expected
    assert f"Copied {len(expected)} files" in message
    assert "~/atomfield/agent start" in message
    assert os.access(shortcut, os.X_OK)


def test_the_shortcut_runs_the_copied_agent_from_any_folder(tmp_path: Path):
    """
    ``~/atomfield/agent`` runs the agent from ``~/atomfield/code`` with
    the Python it was given, from a folder that is not the agent's,
    and the agent names the shortcut as its command.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    env = cluster_environment(tmp_path)
    run_python(
        ["-m", "agent.ship", "mycluster", "--python", sys.executable], env
    )

    done = run_shortcut(tmp_path, env, "--help")

    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("usage: ~/atomfield/agent")


def test_the_shortcut_names_a_missing_python(tmp_path: Path):
    """
    Before the agent's environment exists, the shortcut says so
    instead of failing obscurely.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    env = cluster_environment(tmp_path)
    run_python(["-m", "agent.ship", "mycluster"], env)

    done = run_shortcut(tmp_path, env, "status")

    assert done.returncode == 1
    assert "No Python at" in done.stderr
    assert "atomfield/env/bin/python" in done.stderr
