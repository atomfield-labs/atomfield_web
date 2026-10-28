"""
What a cluster gets: ``python -m agent.ship`` copies the files the
agent loads, which are its package and six small files of app, and
nothing of the server (FastAPI, SQLAlchemy, Redis). Both tests run the
agent in a fresh interpreter, as on a cluster.
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


def test_the_agent_needs_only_its_package_and_six_app_files():
    """
    Outside ``agent/``, the agent loads exactly six files of app, and
    no server package at all.
    """
    loaded = json.loads(run_python(["-c", PROBE]).stdout)
    files = loaded["files"]
    outside = {name for name in files if not name.startswith("agent/")}

    assert outside == APP_FILES
    assert not SERVER_PACKAGES & set(loaded["packages"])


def test_ship_copies_the_agent_and_replaces_the_old_copy(tmp_path: Path):
    """
    Through a fake ssh, ``~/atomfield/code`` ends up holding exactly
    the agent's files; a file from an older copy is gone.

    :param tmp_path: Empty directory for this test.
    :type tmp_path: Path
    """
    fake = tmp_path / "bin" / "ssh"
    fake.parent.mkdir()
    fake.write_text(FAKE_SSH)
    fake.chmod(0o755)
    code = tmp_path / "home" / "atomfield" / "code"
    code.mkdir(parents=True)
    (code / "stale.py").write_text("old copy")
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
    }

    message = run_python(["-m", "agent.ship", "mycluster"], env).stdout
    expected = json.loads(run_python(["-c", PROBE]).stdout)["files"]
    copied = sorted(
        path.relative_to(code).as_posix()
        for path in code.rglob("*")
        if path.is_file()
    )
    assert copied == expected
    assert f"Copied {len(expected)} files" in message
