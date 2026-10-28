"""
Fake ``sbatch``, ``squeue``, ``sacct`` and ``scancel`` for tests: real
commands on ``PATH`` that run batch scripts as local background jobs
and keep their state in a folder (``FAKE_SLURM_STATE``).

Switches, as environment variables:

- ``FAKE_SLURM_PENDING_SECONDS``: jobs wait this long "in the queue";
- ``FAKE_SLURM_NO_ACCOUNTING``: ``sacct`` fails, as on clusters
  without accounting;
- ``FAKE_SLURM_SQUEUE_DOWN``: ``squeue`` fails while this file exists;
- ``FAKE_SLURM_REJECT``: ``sbatch`` refuses jobs with this message;
- ``FAKE_SLURM_FINAL_STATE``: ``sacct`` reports this state for every
  finished job (e.g. ``TIMEOUT``, as when Slurm hits ``--time``).
"""

import os
import stat
import sys
from pathlib import Path

PRELUDE = """#!{python}
import os, re, shlex, signal, subprocess, sys
from pathlib import Path

STATE = Path(os.environ["FAKE_SLURM_STATE"])
STATE.mkdir(parents=True, exist_ok=True)


def alive(job):
    try:
        os.killpg(int((STATE / f"{{job}}.pid").read_text()), 0)
        return True
    except (OSError, ValueError):
        return False


def jobs():
    return sorted(path.stem for path in STATE.glob("*.pid"))
"""

SBATCH = """
reason = os.environ.get("FAKE_SLURM_REJECT")
if reason:
    print(f"sbatch: error: {{reason}}", file=sys.stderr)
    sys.exit(1)
script = Path(sys.argv[-1])
text = script.read_text()
chdir = re.search(r"--chdir=(\\S+)", text).group(1)
output = re.search(r"--output=(\\S+)", text).group(1)
counter = STATE / "next_id"
job = int(counter.read_text()) if counter.exists() else 1000
counter.write_text(str(job + 1))
delay = os.environ.get("FAKE_SLURM_PENDING_SECONDS", "0")
started = shlex.quote(str(STATE / f"{{job}}.started"))
exit_file = shlex.quote(str(STATE / f"{{job}}.exit"))
body = (
    f"sleep {{delay}}; touch {{started}}; "
    f"bash {{shlex.quote(str(script))}} > {{shlex.quote(output)}} 2>&1; "
    f"echo $? > {{exit_file}}"
)
process = subprocess.Popen(
    ["bash", "-c", body], cwd=chdir, start_new_session=True,
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
(STATE / f"{{job}}.pid").write_text(str(process.pid))
print(job)
"""

SQUEUE = """
if os.path.exists(os.environ.get("FAKE_SLURM_SQUEUE_DOWN", "/nonexistent")):
    print("squeue: error: slurm_load_jobs error: timeout", file=sys.stderr)
    sys.exit(1)
for job in jobs():
    if (STATE / f"{{job}}.exit").exists() or not alive(job):
        continue
    running = (STATE / f"{{job}}.started").exists()
    print(f"{{job}}|{{'RUNNING' if running else 'PENDING'}}")
"""

SACCT = """
if os.environ.get("FAKE_SLURM_NO_ACCOUNTING"):
    print("sacct: error: accounting storage is disabled", file=sys.stderr)
    sys.exit(1)
job = next(
    arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--jobs=")
)
exit_file = STATE / f"{{job}}.exit"
if (STATE / f"{{job}}.cancelled").exists():
    print(f"{{job}}|CANCELLED by 0|0:15")
elif exit_file.exists() and os.environ.get("FAKE_SLURM_FINAL_STATE"):
    print(f"{{job}}|{{os.environ['FAKE_SLURM_FINAL_STATE']}}|0:15")
elif exit_file.exists():
    code = int(exit_file.read_text().strip() or 1)
    print(f"{{job}}|{{'COMPLETED' if code == 0 else 'FAILED'}}|{{code}}:0")
elif alive(job):
    print(f"{{job}}|RUNNING|0:0")
"""

SCANCEL = """
job = sys.argv[1]
(STATE / f"{{job}}.cancelled").touch()
try:
    os.killpg(int((STATE / f"{{job}}.pid").read_text()), signal.SIGTERM)
except (OSError, ValueError):
    pass
"""

COMMANDS = {
    "sbatch": SBATCH,
    "squeue": SQUEUE,
    "sacct": SACCT,
    "scancel": SCANCEL,
}


def install_fake_slurm(root: Path) -> dict[str, str]:
    """
    Write the fake commands and return an environment that uses them.

    :param root: Empty folder for the commands and their state.
    :type root: Path
    :return: Environment with the fakes first on ``PATH``.
    :rtype: dict[str, str]
    """
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    prelude = PRELUDE.format(python=sys.executable)
    for name, body in COMMANDS.items():
        path = bin_dir / name
        path.write_text(prelude + body.format())
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_SLURM_STATE": str(root / "state"),
    }
