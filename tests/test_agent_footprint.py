"""
What a cluster needs to run the agent: the agent package and six
small files of app, and nothing of the server (FastAPI, SQLAlchemy,
Redis). The setup guide copies exactly these files; this test keeps
that list true.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# docs/cluster-agent.md, step 1, copies these besides agent/*.py.
APP_FILES = {
    "app/__init__.py",
    "app/agents/__init__.py",
    "app/agents/schemas.py",
    "app/catalog/__init__.py",
    "app/catalog/argv.py",
    "app/catalog/models.py",
}
SERVER_PACKAGES = {"alembic", "asyncpg", "fastapi", "redis", "sqlalchemy"}
# Loads the agent's command line (which loads all of the agent) and
# lists the repository files and top-level packages it pulled in.
PROBE = """
import json, sys
from pathlib import Path
import agent.__main__
root = Path.cwd().resolve()
files = set()
for module in list(sys.modules.values()):
    path = Path(getattr(module, "__file__", None) or "/").resolve()
    if path.is_relative_to(root) and ".venv" not in path.parts:
        files.add(str(path.relative_to(root)))
packages = sorted({name.split(".")[0] for name in sys.modules})
print(json.dumps({"files": sorted(files), "packages": packages}))
"""


def test_the_agent_needs_only_its_package_and_six_app_files():
    """
    Outside ``agent/``, the agent loads exactly the files the guide
    copies, and no server package at all.
    """
    done = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(done.stdout)
    outside = {
        name for name in loaded["files"] if not name.startswith("agent/")
    }

    assert outside == APP_FILES
    assert not SERVER_PACKAGES & set(loaded["packages"])
