"""
Job workspaces: one folder per job inside its session folder, with the
session's uploads copied in and parent workspaces linked under
``upstream/``.

A retried attempt starts in a fresh folder; the previous attempt's
folder is renamed ``job_<id>.try<n>``, so a still-running old process
can never mix its files with the new attempt's.
"""

import os
import shutil
from pathlib import Path
from typing import Any

from app.core.identifiers import sanitize_identifier

UPSTREAM_DIR = "upstream"
EXECUTION_LOG = "execution.log"
LOG_TAIL_CHARACTERS = 1000


def copy_session_inputs(session_dir: Path, job_dir: Path) -> None:
    """
    Copy the session's uploaded files into one job's workspace.

    :param session_dir: Session folder holding uploaded files.
    :type session_dir: Path
    :param job_dir: The job's own workspace.
    :type job_dir: Path
    """
    if not session_dir.is_dir():
        return
    for item in session_dir.iterdir():
        destination = job_dir / item.name
        if item.is_file() and not destination.exists():
            shutil.copy2(item, destination)


def link_directory(link: Path, target: Path) -> None:
    """
    Create a directory symlink unless something already exists there.

    A failed link is skipped: the script then reports the missing file
    itself, with a clearer message than a link error would give.

    :param link: Path of the new symlink.
    :type link: Path
    :param target: Directory it should point to.
    :type target: Path
    """
    if link.exists():
        return
    try:
        link.symlink_to(target.resolve(), target_is_directory=True)
    except OSError:
        pass


def link_upstream_workspaces(
    session_dir: Path,
    job_workspace: Path,
    parameters: dict[str, Any],
) -> None:
    """
    Link each parent's workspace, and its own ancestors, under
    ``upstream/`` so scripts can find upstream files without copies.

    :param session_dir: Session folder holding every job workspace.
    :type session_dir: Path
    :param job_workspace: The job's own workspace.
    :type job_workspace: Path
    :param parameters: Job parameters with optional ``upstream_results``.
    :type parameters: dict[str, Any]
    """
    upstream_results = parameters.get("upstream_results")
    if not isinstance(upstream_results, dict) or not upstream_results:
        return
    upstream_root = job_workspace / UPSTREAM_DIR
    upstream_root.mkdir(parents=True, exist_ok=True)
    for parent_id in upstream_results:
        name = f"job_{sanitize_identifier(str(parent_id))}"
        parent_workspace = session_dir / name
        if not parent_workspace.is_dir():
            continue
        link_directory(upstream_root / name, parent_workspace)
        ancestors = parent_workspace / UPSTREAM_DIR
        for ancestor in ancestors.iterdir() if ancestors.is_dir() else ():
            link_directory(upstream_root / ancestor.name, ancestor)


def session_folder(artifacts_dir: Path, parameters: dict[str, Any]) -> Path:
    """
    Locate a job's session folder from its stored parameters.

    :param artifacts_dir: Root of all workspaces on this machine.
    :type artifacts_dir: Path
    :param parameters: Job parameters with ``pipeline_id``/``user_id``.
    :type parameters: dict[str, Any]
    :return: Session folder path.
    :rtype: Path
    """
    folder = artifacts_dir
    if parameters.get("user_id"):
        folder /= sanitize_identifier(str(parameters["user_id"]))
    return folder / sanitize_identifier(str(parameters["pipeline_id"]))


def retire_previous_attempt(workspace: Path, attempt: int) -> None:
    """
    Move the last attempt's folder aside so this attempt starts empty.

    :param workspace: The job's workspace path.
    :type workspace: Path
    :param attempt: The attempt about to start.
    :type attempt: int
    """
    if attempt > 1 and workspace.exists():
        workspace.rename(
            workspace.with_name(f"{workspace.name}.try{attempt - 1}")
        )


def prepare_workspace(
    artifacts_dir: Path,
    parameters: dict[str, Any],
    job_id: str,
    attempt: int = 1,
) -> tuple[str, Path]:
    """
    Create the job's workspace for one attempt inside its session.

    :param artifacts_dir: Root of all workspaces on this machine.
    :type artifacts_dir: Path
    :param parameters: Job parameters with ``pipeline_id``/``user_id``.
    :type parameters: dict[str, Any]
    :param job_id: Job id.
    :type job_id: str
    :param attempt: Attempt number; above 1, the old folder is retired.
    :type attempt: int
    :return: Pipeline id and the job's workspace path.
    :rtype: tuple[str, Path]
    """
    parameters = {"pipeline_id": f"job_{job_id}", **parameters}
    session_dir = session_folder(artifacts_dir, parameters)
    workspace = session_dir / f"job_{sanitize_identifier(str(job_id))}"
    retire_previous_attempt(workspace, attempt)
    workspace.mkdir(parents=True, exist_ok=True)
    copy_session_inputs(session_dir, workspace)
    link_upstream_workspaces(session_dir, workspace, parameters)
    return session_dir.name, workspace


def build_environment(pack_source_dir: Path) -> dict[str, str]:
    """
    Environment for a task: unbuffered output, pack importable.

    :param pack_source_dir: Directory containing the pack's packages.
    :type pack_source_dir: Path
    :return: Environment variables for the subprocess.
    :rtype: dict[str, str]
    """
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    paths = [str(pack_source_dir), environment.get("PYTHONPATH", "")]
    environment["PYTHONPATH"] = os.pathsep.join(path for path in paths if path)
    return environment


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
