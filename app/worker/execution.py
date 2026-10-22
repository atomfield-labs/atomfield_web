"""
Run one catalog task as a subprocess inside its job workspace.

The command comes from the task's definition (``build_argv``), so this
module knows nothing about any particular script: a new task in the
catalog runs here without a code change.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.catalog.argv import Invocation, build_argv
from app.catalog.models import TaskDefinition
from app.core.config import settings
from app.services.job_service import sanitize_identifier

BASE_DIR = Path(__file__).resolve().parents[2]
PACK_SOURCE_DIR = BASE_DIR / "scripts_repo" / "src"
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


def prepare_workspace(
    parameters: dict[str, Any],
    job_id: str,
) -> tuple[str, Path]:
    """
    Create the job's workspace inside its session folder.

    :param parameters: Job parameters with ``pipeline_id``/``user_id``.
    :type parameters: dict[str, Any]
    :param job_id: Job id.
    :type job_id: str
    :return: Pipeline id and the job's workspace path.
    :rtype: tuple[str, Path]
    """
    pipeline_id = sanitize_identifier(
        str(parameters.get("pipeline_id", f"job_{job_id}"))
    )
    session_dir = Path(settings.ARTIFACTS_DIR)
    if parameters.get("user_id"):
        session_dir /= sanitize_identifier(str(parameters["user_id"]))
    session_dir /= pipeline_id
    workspace = session_dir / f"job_{sanitize_identifier(str(job_id))}"
    workspace.mkdir(parents=True, exist_ok=True)
    copy_session_inputs(session_dir, workspace)
    link_upstream_workspaces(session_dir, workspace, parameters)
    return pipeline_id, workspace


def resolve_python_executable() -> str:
    """
    Pick the interpreter of the domain pack's environment.

    :return: Configured interpreter, or this one if it does not exist.
    :rtype: str
    """
    configured = settings.CHEMISTRY_PYTHON_BIN
    return configured if os.path.exists(configured) else sys.executable


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


def run_logged(
    argv: list[str],
    workspace: Path,
    log_path: Path,
    environment: dict[str, str],
) -> int:
    """
    Run a command in the workspace, sending all output to a log file.

    :param argv: Command, as built by ``build_argv``.
    :type argv: list[str]
    :param workspace: Working directory.
    :type workspace: Path
    :param log_path: File that receives stdout and stderr.
    :type log_path: Path
    :param environment: Environment variables.
    :type environment: dict[str, str]
    :return: Exit code.
    :rtype: int
    """
    with log_path.open("w", encoding="utf-8") as log_stream:
        process = subprocess.run(
            argv,
            cwd=workspace,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            env=environment,
            check=False,
        )
    return process.returncode


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


def failure_result(
    task: TaskDefinition,
    workspace: Path,
    return_code: int,
) -> dict[str, Any]:
    """
    Describe a failed run, preferring the script's own log.

    :param task: Task that ran.
    :type task: TaskDefinition
    :param workspace: The job's workspace.
    :type workspace: Path
    :param return_code: Exit code of the script.
    :type return_code: int
    :return: Failure result for the worker.
    :rtype: dict[str, Any]
    """
    detail = (
        read_tail(workspace / f"{task.id}.log")
        or read_tail(workspace / EXECUTION_LOG)
        or f"Process exited with code {return_code}"
    )
    message = f"{task.id} failed (code {return_code}):\n{detail}"
    return {"status": "failed", "error": message}


def success_result(
    task: TaskDefinition,
    workspace: Path,
    pipeline_id: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Describe a successful run and list the files it left behind.

    :param task: Task that ran.
    :type task: TaskDefinition
    :param workspace: The job's workspace.
    :type workspace: Path
    :param pipeline_id: Pipeline the job belongs to.
    :type pipeline_id: str
    :param job_id: Job id.
    :type job_id: str
    :return: Success result for the worker.
    :rtype: dict[str, Any]
    """
    artifacts = sorted(
        item.name
        for item in workspace.iterdir()
        if item.is_file() and not item.name.startswith(".")
    )
    script_log = f"{task.id}.log"
    has_script_log = (workspace / script_log).exists()
    output = {
        "status": "simulation_complete",
        "script": task.id,
        "logfile": script_log if has_script_log else EXECUTION_LOG,
        "pipeline_id": pipeline_id,
        "job_id": job_id,
        "artifacts": artifacts,
    }
    return {"status": "success", "output": output}


def run_catalog_task(
    task: TaskDefinition,
    parameters: dict[str, Any],
    input_files: dict[str, list[str]],
    job_id: str,
) -> dict[str, Any]:
    """
    Run one job of a catalog task from start to finish.

    :param task: Task definition.
    :type task: TaskDefinition
    :param parameters: Stored job parameters (validated values plus
        platform bookkeeping, which ``build_argv`` ignores).
    :type parameters: dict[str, Any]
    :param input_files: Input port name -> uploaded file names.
    :type input_files: dict[str, list[str]]
    :param job_id: Job id.
    :type job_id: str
    :return: Success or failure result for the worker.
    :rtype: dict[str, Any]
    """
    pipeline_id, workspace = prepare_workspace(parameters, job_id)
    invocation = Invocation(
        values=parameters,
        inputs=input_files,
        job_name=task.id,
        cpus=task.resources.cpus,
    )
    argv = build_argv(task, invocation, resolve_python_executable())
    environment = build_environment(PACK_SOURCE_DIR)
    return_code = run_logged(
        argv, workspace, workspace / EXECUTION_LOG, environment
    )
    if return_code != 0:
        return failure_result(task, workspace, return_code)
    return success_result(task, workspace, pipeline_id, job_id)
