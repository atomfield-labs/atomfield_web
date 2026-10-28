"""
Job folders on the agent's machine: one folder per run, one folder per
job inside it, named after the job's node in the pipeline::

    <artifacts>/runs/<run id>/
        opt/        water.xyz (downloaded), opt.log, outputs ...
        md/         md.log, trajectory, upstream/opt -> ../opt

Everything of a job sits together in its folder (inputs, outputs,
logs). Parents are linked under ``upstream/``, never copied: one run
runs on one machine, so their folders are right beside.

A retried attempt starts in a fresh folder; the previous attempt's
folder is renamed ``<node>.try<n>``, so a still-running old process
can never mix its files with the new attempt's.
"""

import os
from pathlib import Path
from typing import Any

from app.agents.schemas import EXECUTION_LOG, JobAssignment

RUNS_DIR = "runs"
UPSTREAM_DIR = "upstream"
# Downloaded once and kept: scripts releases and data packs.
RELEASES_DIR = "releases"
DATA_DIR = "data"
LOG_TAIL_CHARACTERS = 1000


def require_plain_name(name: str) -> str:
    """
    Accept a folder or file name from the server only if it cannot
    point anywhere else (no separators, not ``.`` or ``..``).

    :param name: Node key or file name.
    :type name: str
    :return: The name, unchanged.
    :rtype: str
    :raises ValueError: If the name is a path.
    """
    if name in {"", ".", ".."} or Path(name).name != name or "\\" in name:
        raise ValueError(f"Not a plain name: {name!r}")
    return name


def run_folder(artifacts_dir: Path, run_id: object) -> Path:
    """
    The folder holding every job of one run.

    :param artifacts_dir: Root of all runs on this machine.
    :type artifacts_dir: Path
    :param run_id: The run.
    :type run_id: object
    :return: ``<artifacts>/runs/<run id>``.
    :rtype: Path
    """
    return artifacts_dir / RUNS_DIR / str(run_id)


def link_directory(link: Path, target: Path) -> None:
    """
    Create a relative directory symlink unless something already
    exists there. Relative (``../../opt``), so the run folder can be
    copied anywhere (rsync to a laptop) with its links still working.

    A failed link is skipped: the script then reports the missing file
    itself, with a clearer message than a link error would give.

    :param link: Where the link goes.
    :type link: Path
    :param target: Directory it points to.
    :type target: Path
    """
    if link.exists():
        return
    relative = os.path.relpath(target.resolve(), link.parent.resolve())
    try:
        link.symlink_to(relative, target_is_directory=True)
    except OSError:
        pass


def link_parents(run_dir: Path, workspace: Path, parents: list[str]) -> None:
    """
    Link each parent's folder, and its own ancestors, under
    ``upstream/`` so scripts find upstream files without copies.

    :param run_dir: The run's folder.
    :type run_dir: Path
    :param workspace: This job's folder.
    :type workspace: Path
    :param parents: Parent node keys.
    :type parents: list[str]
    """
    if not parents:
        return
    upstream_root = workspace / UPSTREAM_DIR
    upstream_root.mkdir(parents=True, exist_ok=True)
    for parent in parents:
        parent_dir = run_dir / require_plain_name(parent)
        if not parent_dir.is_dir():
            continue
        link_directory(upstream_root / parent, parent_dir)
        ancestors = parent_dir / UPSTREAM_DIR
        for ancestor in ancestors.iterdir() if ancestors.is_dir() else ():
            link_directory(upstream_root / ancestor.name, ancestor)


def retire_previous_attempt(workspace: Path, attempt: int) -> None:
    """
    Move the last attempt's folder aside so this attempt starts empty.

    :param workspace: The job's folder.
    :type workspace: Path
    :param attempt: The attempt about to start.
    :type attempt: int
    """
    if attempt > 1 and workspace.exists():
        workspace.rename(
            workspace.with_name(f"{workspace.name}.try{attempt - 1}")
        )


def job_folder(artifacts_dir: Path, assignment: JobAssignment) -> Path:
    """
    Where a job's folder is, without touching it (for a job a previous
    agent started).

    :param artifacts_dir: Root of all runs on this machine.
    :type artifacts_dir: Path
    :param assignment: The job's attempt.
    :type assignment: JobAssignment
    :return: ``<artifacts>/runs/<run>/<node>``.
    :rtype: Path
    """
    run_dir = run_folder(artifacts_dir, assignment.run_id)
    return run_dir / require_plain_name(assignment.node_key)


def prepare_workspace(artifacts_dir: Path, assignment: JobAssignment) -> Path:
    """
    Create a job's folder for one attempt, with its parents linked.
    Inputs are downloaded into it afterwards.

    :param artifacts_dir: Root of all runs on this machine.
    :type artifacts_dir: Path
    :param assignment: The attempt to prepare for.
    :type assignment: JobAssignment
    :return: The job's folder.
    :rtype: Path
    """
    run_dir = run_folder(artifacts_dir, assignment.run_id)
    workspace = job_folder(artifacts_dir, assignment)
    retire_previous_attempt(workspace, assignment.attempt)
    workspace.mkdir(parents=True, exist_ok=True)
    link_parents(run_dir, workspace, assignment.parents)
    return workspace


def job_environment(pack_source_dir: Path) -> dict[str, str]:
    """
    Variables a job needs on top of its usual environment: unbuffered
    output, and the domain pack importable.

    :param pack_source_dir: Directory containing the pack's packages.
    :type pack_source_dir: Path
    :return: The additions only.
    :rtype: dict[str, str]
    """
    paths = [str(pack_source_dir), os.environ.get("PYTHONPATH", "")]
    return {
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.pathsep.join(path for path in paths if path),
    }


def read_tail(path: Path, max_characters: int = LOG_TAIL_CHARACTERS) -> str:
    """
    Read the end of a log file, or nothing if it does not exist.

    :param path: Log file.
    :type path: Path
    :param max_characters: How much of the end to keep.
    :type max_characters: int
    :return: Last characters of the file.
    :rtype: str
    """
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[-max_characters:]


def failure_message(task_id: str, workspace: Path, return_code: int) -> str:
    """
    Describe a failed run, preferring the script's own log.

    :param task_id: Task that ran.
    :type task_id: str
    :param workspace: The job's workspace.
    :type workspace: Path
    :param return_code: Exit code of the script.
    :type return_code: int
    :return: Error message for the job record.
    :rtype: str
    """
    detail = (
        read_tail(workspace / f"{task_id}.log")
        or read_tail(workspace / EXECUTION_LOG)
        or f"Process exited with code {return_code}"
    )
    return f"{task_id} failed (code {return_code}):\n{detail}"


def success_output(
    task_id: str,
    workspace: Path,
    pipeline_id: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Describe a successful run and list the files it left behind.

    :param task_id: Task that ran.
    :type task_id: str
    :param workspace: The job's workspace.
    :type workspace: Path
    :param pipeline_id: Pipeline the job belongs to.
    :type pipeline_id: str
    :param job_id: Job id.
    :type job_id: str
    :return: Output payload for the job record.
    :rtype: dict[str, Any]
    """
    artifacts = sorted(
        item.name
        for item in workspace.iterdir()
        if item.is_file() and not item.name.startswith(".")
    )
    script_log = f"{task_id}.log"
    has_script_log = (workspace / script_log).exists()
    return {
        "status": "simulation_complete",
        "script": task_id,
        "logfile": script_log if has_script_log else EXECUTION_LOG,
        "pipeline_id": pipeline_id,
        "job_id": job_id,
        "artifacts": artifacts,
    }
