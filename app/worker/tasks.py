"""
Background execution worker tasks for ARQ.
Handles job execution in isolated containers or native chemistry drivers.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import docker
from docker.errors import ContainerError, DockerException, ImageNotFound

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.job_service import (
    evaluate_downstream_dependencies,
    mark_job_failed,
    mark_job_running,
    mark_job_success,
    sanitize_identifier,
)

DOCKER_PYTHON_IMAGE = "python:3.11-slim"
NANOREACTOR_SCRIPT_NAME = "xtb_nanoreactor"
NANOREACTOR_LOG_NAME = "nanoreactor.log"
MEMORY_LIMIT_512M = "512m"

CHEMISTRY_DRIVERS: dict[str, str] = {
    "xtb_opt": "afscripts.scripts.xtbopt_driver",
    "xtbopt_driver": "afscripts.scripts.xtbopt_driver",
    "xtb_md": "afscripts.scripts.xtbmd_driver",
    "xtbmd_driver": "afscripts.scripts.xtbmd_driver",
    "rxn_network": "afscripts.scripts.rxn_network_driver",
    "rxn_network_driver": "afscripts.scripts.rxn_network_driver",
    "mlff_refine": "afscripts.scripts.mlff_refine_driver",
    "mlff_refine_driver": "afscripts.scripts.mlff_refine_driver",
    "ts_search": "afscripts.scripts.ts_search_driver",
    "ts_search_driver": "afscripts.scripts.ts_search_driver",
    "mlff_opt": "afscripts.scripts.mlff_opt",
}

BASE_DIR = Path(__file__).resolve().parents[2]
HOST_SCRIPTS_DIR = os.getenv("HOST_SCRIPTS_DIR", settings.HOST_SCRIPTS_DIR)
HOST_ARTIFACTS_DIR = os.getenv(
    "HOST_ARTIFACTS_DIR", settings.HOST_ARTIFACTS_DIR
)

_docker_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    """
    Acquire or instantiate lazy Docker client singleton.

    :return: Active Docker client connection instance.
    :rtype: docker.DockerClient
    :raises RuntimeError: If Docker daemon is unavailable.
    """
    global _docker_client
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
        except Exception as client_exc:
            error_message = f"Docker client initialization failed: {client_exc}"
            raise RuntimeError(error_message) from client_exc
    return _docker_client


def _copy_session_inputs_to_job(session_dir: Path, job_dir: Path) -> None:
    """
    Copy session input structure files into isolated job directory.

    :param session_dir: Root session directory containing uploaded inputs.
    :type session_dir: Path
    :param job_dir: Destination execution directory for the job run.
    :type job_dir: Path
    """
    if not session_dir.is_dir():
        return
    for item in session_dir.iterdir():
        if item.is_file():
            destination = job_dir / item.name
            if not destination.exists():
                shutil.copy2(item, destination)


def _link_upstream_workspaces(
    session_dir: Path,
    job_workspace: Path,
    parameters: dict[str, Any],
) -> None:
    """
    Symlink parent job output directories into `upstream/job_<parent_id>`
    to provide zero-copy access to all parent and ancestor workspace artifacts.

    :param session_dir: Root session directory containing all job workspaces.
    :type session_dir: Path
    :param job_workspace: Execution workspace directory for the current job.
    :type job_workspace: Path
    :param parameters: Job parameters dictionary containing optional upstream_results.
    :type parameters: dict[str, Any]
    """
    upstream_results = parameters.get("upstream_results")
    if not isinstance(upstream_results, dict) or not upstream_results:
        return

    upstream_root = job_workspace / "upstream"
    upstream_root.mkdir(parents=True, exist_ok=True)

    for parent_id in upstream_results:
        clean_parent_id = sanitize_identifier(str(parent_id))
        parent_workspace = session_dir / f"job_{clean_parent_id}"
        if not parent_workspace.is_dir():
            continue

        target_symlink = upstream_root / f"job_{clean_parent_id}"
        if not target_symlink.exists():
            try:
                target_symlink.symlink_to(
                    parent_workspace.resolve(), target_is_directory=True
                )
            except OSError:
                pass

        # Also link transitive ancestors if parent has its own upstream/
        parent_upstream = parent_workspace / "upstream"
        if parent_upstream.is_dir():
            for ancestor_dir in parent_upstream.iterdir():
                ancestor_symlink = upstream_root / ancestor_dir.name
                if not ancestor_symlink.exists():
                    try:
                        ancestor_symlink.symlink_to(
                            ancestor_dir.resolve(), target_is_directory=True
                        )
                    except OSError:
                        pass


def _resolve_workspace_dir(
    parameters: dict[str, Any],
    job_id: str,
) -> tuple[str, Path]:
    """
    Resolve and construct isolated job execution workspace inside session.

    :param parameters: Pipeline or job parameter dictionary.
    :type parameters: dict[str, Any]
    :param job_id: Unique identifier string for the executing job.
    :type job_id: str
    :return: Tuple of sanitized pipeline ID and filesystem workspace Path.
    :rtype: tuple[str, Path]
    """
    raw_user = parameters.get("user_id")
    raw_identifier = parameters.get("pipeline_id", f"job_{job_id}")
    pipeline_id = sanitize_identifier(raw_identifier)
    if raw_user:
        clean_user = sanitize_identifier(str(raw_user))
        session_dir = Path(HOST_ARTIFACTS_DIR) / clean_user / pipeline_id
    else:
        session_dir = Path(HOST_ARTIFACTS_DIR) / pipeline_id

    session_dir.mkdir(parents=True, exist_ok=True)
    clean_job_id = sanitize_identifier(str(job_id))
    job_workspace = session_dir / f"job_{clean_job_id}"
    job_workspace.mkdir(parents=True, exist_ok=True)
    _copy_session_inputs_to_job(session_dir, job_workspace)
    _link_upstream_workspaces(session_dir, job_workspace, parameters)
    return pipeline_id, job_workspace



def _is_nanoreactor_task(script_name: str, driver_path: Path) -> bool:
    """
    Determine whether script name matches xTB nanoreactor driver.

    :param script_name: Name of the script to execute.
    :type script_name: str
    :param driver_path: Filesystem path to nanoreactor driver script.
    :type driver_path: Path
    :return: True if task should run via nanoreactor driver.
    :rtype: bool
    """
    is_named = (
        script_name in ["xtb_nanoreactor.py", "xtb_nanoreactor"]
        or "nanoreactor" in script_name
    )
    return is_named and driver_path.exists()


def _find_structure_by_param(
    workspace_dir: Path,
    input_filename: str | None,
) -> Path | None:
    """
    Locate input structure file specified explicitly in parameters.

    :param workspace_dir: Directory containing workspace artifacts.
    :type workspace_dir: Path
    :param input_filename: File path or name provided in parameters.
    :type input_filename: str | None
    :return: Resolved Path if file exists, else None.
    :rtype: Path | None
    """
    if not input_filename:
        return None
    clean_target = input_filename.replace("/workspace/", "").replace(
        "workspace/", ""
    )
    clean_name = Path(clean_target).name
    candidate_path = workspace_dir / clean_name
    return candidate_path if candidate_path.exists() else None


def _find_structure_by_extension(workspace_dir: Path) -> Path | None:
    """
    Scan workspace directory for molecular structure files by extension.

    :param workspace_dir: Directory containing workspace artifacts.
    :type workspace_dir: Path
    :return: First matching structure file path, or None if not found.
    :rtype: Path | None
    """
    for extension in [".xyz", ".mol", ".sdf", ".cif", ".pdb"]:
        matched_files = list(workspace_dir.glob(f"*{extension}"))
        if matched_files:
            return matched_files[0]
    return None


def _resolve_input_structure(
    workspace_dir: Path,
    parameters: dict[str, Any],
) -> Path | None:
    """
    Resolve molecular input structure file from parameters or workspace.

    :param workspace_dir: Directory containing workspace artifacts.
    :type workspace_dir: Path
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Resolved input file Path or None.
    :rtype: Path | None
    """
    param_input = parameters.get("input")
    resolved_path = _find_structure_by_param(workspace_dir, param_input)
    if resolved_path is not None:
        return resolved_path
    return _find_structure_by_extension(workspace_dir)


def _resolve_python_executable() -> str:
    """
    Identify chemistry Python binary or fallback to current interpreter.

    :return: Filesystem path to target Python executable.
    :rtype: str
    """
    configured_binary = os.getenv(
        "CHEMISTRY_PYTHON_BIN", settings.CHEMISTRY_PYTHON_BIN
    )
    if os.path.exists(configured_binary):
        return configured_binary
    return sys.executable


def _build_simulation_flags(parameters: dict[str, Any]) -> list[str]:
    """
    Construct runtime simulation flags for xTB nanoreactor driver.

    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Command flag argument list tokens.
    :rtype: list[str]
    """
    flag_specs = [
        ("-nreplicates", "nreplicates", 1),
        ("-workers", "workers", 1),
        ("-time", "time", 0.2),
        ("-step", "step", 1.0),
        ("-temp", "temp", 1000.0),
    ]
    flags = [
        token
        for flag, key, default in flag_specs
        for token in (flag, str(parameters.get(key, default)))
    ]
    return flags + ["-JOBNAME", "nanoreactor"]


def _build_nanoreactor_command(
    python_bin: str,
    input_path: Path,
    parameters: dict[str, Any],
) -> list[str]:
    """
    Construct subprocess command arguments for xTB nanoreactor.

    :param python_bin: Path to Python binary executable.
    :type python_bin: str
    :param input_path: Path to molecular input structure.
    :type input_path: Path
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: List of command-line argument tokens.
    :rtype: list[str]
    """
    driver_module = "afscripts.scripts.xtb_nanoreactor"
    prefix_args = [python_bin, "-u", "-m", driver_module, "-i", str(input_path)]
    return prefix_args + _build_simulation_flags(parameters)


def _build_nanoreactor_env(scripts_repo_dir: Path) -> dict[str, str]:
    """
    Assemble environment variables for nanoreactor driver execution.

    :param scripts_repo_dir: Root directory of scripts repository.
    :type scripts_repo_dir: Path
    :return: Environment dictionary configured for unbuffered execution.
    :rtype: dict[str, str]
    """
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    existing_pythonpath = environment.get("PYTHONPATH", "")
    if existing_pythonpath:
        environment["PYTHONPATH"] = f"{scripts_repo_dir}:{existing_pythonpath}"
    else:
        environment["PYTHONPATH"] = str(scripts_repo_dir)
    return environment


def _execute_nanoreactor_process(
    command: list[str],
    workspace_dir: Path,
    logfile_path: Path,
    environment: dict[str, str],
) -> int:
    """
    Execute nanoreactor subprocess and pipe combined output to logfile.

    :param command: List of command-line tokens.
    :type command: list[str]
    :param workspace_dir: Working directory for process execution.
    :type workspace_dir: Path
    :param logfile_path: Destination path for stdout and stderr logs.
    :type logfile_path: Path
    :param environment: Process environment variables dictionary.
    :type environment: dict[str, str]
    :return: Subprocess exit code.
    :rtype: int
    """
    with open(logfile_path, "w", encoding="utf-8") as output_log_file:
        process = subprocess.run(
            command,
            cwd=str(workspace_dir),
            stdout=output_log_file,
            stderr=subprocess.STDOUT,
            env=environment,
            text=True,
            check=False,
        )
    return process.returncode


def _read_logfile_tail(logfile_path: Path, max_characters: int = 1000) -> str:
    """
    Read tail end of execution logfile for failure reporting.

    :param logfile_path: Path to target logfile.
    :type logfile_path: Path
    :param max_characters: Maximum trailing character count to retrieve.
    :type max_characters: int
    :return: Truncated log content or fallback description.
    :rtype: str
    """
    if not logfile_path.exists():
        return "No log output."
    log_content = logfile_path.read_text(encoding="utf-8", errors="ignore")
    return log_content[-max_characters:]


def _build_nanoreactor_invocation(
    structure_path: Path,
    parameters: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """
    Assemble command tokens and environment for nanoreactor driver.

    :param structure_path: Resolved path to input molecular structure.
    :type structure_path: Path
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Tuple of subprocess command list and environment dictionary.
    :rtype: tuple[list[str], dict[str, str]]
    """
    python_bin = _resolve_python_executable()
    cmd = _build_nanoreactor_command(python_bin, structure_path, parameters)
    scripts_repo = BASE_DIR / "scripts_repo" / "src"
    env = _build_nanoreactor_env(scripts_repo)
    return cmd, env


def _format_nanoreactor_output(
    structure_name: str,
    pipeline_id: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Format successful output payload for nanoreactor simulation.

    :param structure_name: Filename of the input structure.
    :type structure_name: str
    :param pipeline_id: Pipeline session identifier.
    :type pipeline_id: str
    :param job_id: Executing job identifier.
    :type job_id: str
    :return: Success response mapping.
    :rtype: dict[str, Any]
    """
    return {
        "status": "success",
        "output": {
            "status": "simulation_complete",
            "input": structure_name,
            "logfile": NANOREACTOR_LOG_NAME,
            "pipeline_id": pipeline_id,
            "job_id": job_id,
        },
    }


def _run_nanoreactor_pipeline(
    workspace_dir: Path,
    pipeline_id: str,
    job_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Orchestrate full nanoreactor driver execution sequence.

    :param workspace_dir: Directory containing simulation assets.
    :type workspace_dir: Path
    :param pipeline_id: Sanitized pipeline identifier string.
    :type pipeline_id: str
    :param job_id: Unique job identifier string.
    :type job_id: str
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Result status dictionary with outputs or error message.
    :rtype: dict[str, Any]
    """
    structure_path = _resolve_input_structure(workspace_dir, parameters)
    if not structure_path:
        error_msg = f"No input structure (.xyz) found in {workspace_dir}"
        return {"status": "failed", "error": error_msg}

    cmd, env = _build_nanoreactor_invocation(structure_path, parameters)
    logfile = workspace_dir / NANOREACTOR_LOG_NAME
    return_code = _execute_nanoreactor_process(cmd, workspace_dir, logfile, env)
    if return_code != 0:
        log_tail = _read_logfile_tail(logfile)
        err = f"Nanoreactor failed (code {return_code}):\n{log_tail}"
        return {"status": "failed", "error": err}

    return _format_nanoreactor_output(structure_path.name, pipeline_id, job_id)


def _is_chemistry_task(script_name: str) -> str | None:
    """
    Check if the given script name maps to a Hilbert modular chemistry driver.

    :param script_name: Script identifier string.
    :type script_name: str
    :return: Python module path if matched, else None.
    :rtype: str | None
    """
    clean_name = script_name.replace(".py", "")
    return CHEMISTRY_DRIVERS.get(clean_name)


def _build_chemistry_command(
    python_bin: str,
    driver_module: str,
    script_key: str,
    workspace_dir: Path,
    parameters: dict[str, Any],
) -> list[str]:
    """
    Construct CLI command tokens for invoking a modular chemistry driver.

    :param python_bin: Path to Python binary executable.
    :type python_bin: str
    :param driver_module: Python module path for driver.
    :type driver_module: str
    :param script_key: Clean identifier of the script.
    :type script_key: str
    :param workspace_dir: Filesystem path to job workspace.
    :type workspace_dir: Path
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: List of command-line argument tokens.
    :rtype: list[str]
    """
    cmd = [python_bin, "-u", "-m", driver_module]
    ignored_keys = {
        "pipeline_id",
        "user_id",
        "upstream_results",
        "parent_job_id",
        "parallel_index",
        "parallel_count",
    }

    for key, val in parameters.items():
        if key in ignored_keys or val is None:
            continue
        if key in ["input", "i"]:
            resolved = _find_structure_by_param(workspace_dir, str(val))
            cmd.extend(["-i", str(resolved or val)])
            continue

        if key.lower() == "jobname":
            cmd.extend(["-JOBNAME", str(val)])
            continue

        flag = f"-{key}" if not key.startswith("-") else key
        if isinstance(val, bool):
            if val:
                cmd.append(flag)
        elif isinstance(val, (int, float, str)):
            cmd.extend([flag, str(val)])
        elif isinstance(val, list):
            for item in val:
                cmd.extend([flag, str(item)])

    if not any(k in cmd for k in ["-JOBNAME", "--jobname", "-jobname"]):
        cmd.extend(["-JOBNAME", script_key])

    return cmd


def _format_chemistry_output(
    script_key: str,
    workspace_dir: Path,
    pipeline_id: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Format successful output payload for chemistry driver execution.

    :param script_key: Clean identifier of the script.
    :type script_key: str
    :param workspace_dir: Execution workspace directory.
    :type workspace_dir: Path
    :param pipeline_id: Pipeline session identifier.
    :type pipeline_id: str
    :param job_id: Executing job identifier.
    :type job_id: str
    :return: Success response mapping.
    :rtype: dict[str, Any]
    """
    artifacts = [
        f.name
        for f in workspace_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ]
    logfile_name = f"{script_key}.log"
    active_log = (
        logfile_name
        if (workspace_dir / logfile_name).exists()
        else "execution.log"
    )
    return {
        "status": "success",
        "output": {
            "status": "simulation_complete",
            "script": script_key,
            "logfile": active_log,
            "pipeline_id": pipeline_id,
            "job_id": job_id,
            "artifacts": artifacts,
        },
    }


def _run_chemistry_driver(
    script_key: str,
    driver_module: str,
    workspace_dir: Path,
    pipeline_id: str,
    job_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute modular chemistry driver in workspace and capture outputs.

    :param script_key: Clean identifier of the script.
    :type script_key: str
    :param driver_module: Python module path for driver.
    :type driver_module: str
    :param workspace_dir: Directory containing simulation assets.
    :type workspace_dir: Path
    :param pipeline_id: Sanitized pipeline identifier string.
    :type pipeline_id: str
    :param job_id: Unique job identifier string.
    :type job_id: str
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Result status dictionary with outputs or error message.
    :rtype: dict[str, Any]
    """
    python_bin = _resolve_python_executable()
    scripts_repo = BASE_DIR / "scripts_repo" / "src"
    env = _build_nanoreactor_env(scripts_repo)
    cmd = _build_chemistry_command(
        python_bin, driver_module, script_key, workspace_dir, parameters
    )

    execution_log = workspace_dir / "execution.log"
    return_code = _execute_nanoreactor_process(
        cmd, workspace_dir, execution_log, env
    )

    if return_code != 0:
        script_log = workspace_dir / f"{script_key}.log"
        tail_script = (
            _read_logfile_tail(script_log) if script_log.exists() else ""
        )
        tail_exec = (
            _read_logfile_tail(execution_log) if execution_log.exists() else ""
        )
        error_detail = (
            tail_script
            or tail_exec
            or f"Process exited with code {return_code}"
        )
        return {
            "status": "failed",
            "error": f"{script_key} failed (code {return_code}):\n{error_detail}",
        }

    return _format_chemistry_output(
        script_key, workspace_dir, pipeline_id, job_id
    )


def _pull_docker_image_if_missing(
    client: docker.DockerClient,
    image_tag: str,
) -> None:
    """
    Ensure required Docker container image is present locally.

    :param client: Initialized Docker client connection.
    :type client: docker.DockerClient
    :param image_tag: Container image tag name to check and pull.
    :type image_tag: str
    :return: None
    :rtype: None
    """
    try:
        client.images.get(image_tag)
    except ImageNotFound:
        client.images.pull(image_tag)


def _build_docker_volume_mounts(
    workspace_path: str,
) -> dict[str, dict[str, str]]:
    """
    Construct Docker container volume mount configuration.

    :param workspace_path: Local filesystem host path for workspace.
    :type workspace_path: str
    :return: Docker volume mounting specification mapping.
    :rtype: dict[str, dict[str, str]]
    """
    return {
        HOST_SCRIPTS_DIR: {"bind": "/sandbox", "mode": "ro"},
        workspace_path: {"bind": "/workspace", "mode": "rw"},
    }


def _execute_container(
    client: docker.DockerClient,
    script_name: str,
    volumes: dict[str, dict[str, str]],
    environment: dict[str, str],
) -> str | bytes:
    """
    Execute python script within isolated Docker sandbox container.

    :param client: Active Docker client connection.
    :type client: docker.DockerClient
    :param script_name: Clean filename of simulation script.
    :type script_name: str
    :param volumes: Volume binding configuration map.
    :type volumes: dict[str, dict[str, str]]
    :param environment: Environment variables passed to container.
    :type environment: dict[str, str]
    :return: Raw log output bytes or string.
    :rtype: str | bytes
    """
    return client.containers.run(
        image=DOCKER_PYTHON_IMAGE,
        command=["python", f"/sandbox/{script_name}"],
        volumes=volumes,
        environment=environment,
        remove=True,
        network_disabled=True,
        mem_limit=MEMORY_LIMIT_512M,
        stderr=True,
        stdout=True,
    )


def _parse_container_output(raw_output: str | bytes) -> dict[str, Any]:
    """
    Parse container stdout logs into JSON result dictionary.

    :param raw_output: Raw string or bytes captured from container stdout.
    :type raw_output: str | bytes
    :return: Status dictionary with parsed output or decode error.
    :rtype: dict[str, Any]
    """
    text_output = (
        raw_output.decode("utf-8").strip()
        if isinstance(raw_output, bytes)
        else str(raw_output).strip()
    )
    try:
        parsed_data = json.loads(text_output)
        return {"status": "success", "output": parsed_data}
    except json.JSONDecodeError:
        error_msg = f"Output was not valid JSON. Raw output: {text_output}"
        return {"status": "failed", "error": error_msg}


def _extract_container_error_message(container_error: ContainerError) -> str:
    """
    Extract error message from Docker ContainerError instance.

    :param container_error: Caught container execution exception.
    :type container_error: ContainerError
    :return: Formatted stderr string or error representation.
    :rtype: str
    """
    stderr_bytes = getattr(container_error, "stderr", None)
    if stderr_bytes:
        return stderr_bytes.decode("utf-8", errors="ignore")
    return str(container_error)


def _run_sandbox_container(
    client: docker.DockerClient,
    script_name: str,
    workspace_dir: Path,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Configure and execute sandbox container capturing output or error.

    :param client: Active Docker client connection.
    :type client: docker.DockerClient
    :param script_name: Name of target script inside scripts directory.
    :type script_name: str
    :param workspace_dir: Filesystem path to job workspace.
    :type workspace_dir: Path
    :param parameters: Job execution parameters dictionary.
    :type parameters: dict[str, Any]
    :return: Status dictionary with parsed output or execution failure.
    :rtype: dict[str, Any]
    """
    mounts = _build_docker_volume_mounts(str(workspace_dir))
    env_vars = {"JOB_PARAMS": json.dumps(parameters)}
    clean_name = Path(script_name).name
    try:
        logs = _execute_container(client, clean_name, mounts, env_vars)
        return _parse_container_output(logs)
    except ContainerError as container_exc:
        err_msg = _extract_container_error_message(container_exc)
        return {"status": "failed", "error": f"Container failed: {err_msg}"}
    except (DockerException, OSError) as runtime_exc:
        return {"status": "failed", "error": str(runtime_exc)}


def run_docker_sandbox(
    script_name: str,
    parameters: dict[str, Any] | None,
    job_id: str,
) -> dict[str, Any]:
    """
    Execute script in isolated Docker container with sandbox mounts.

    :param script_name: Name of target script inside scripts directory.
    :type script_name: str
    :param parameters: Optional dictionary of job input parameters.
    :type parameters: dict[str, Any] | None
    :param job_id: Unique job identifier string.
    :type job_id: str
    :return: Status dictionary with output data or execution error.
    :rtype: dict[str, Any]
    """
    params = parameters or {}
    _pipeline_id, workspace_dir = _resolve_workspace_dir(params, job_id)
    client = get_docker_client()
    _pull_docker_image_if_missing(client, DOCKER_PYTHON_IMAGE)
    return _run_sandbox_container(client, script_name, workspace_dir, params)


def run_script_task(
    script_name: str,
    parameters: dict[str, Any] | None,
    job_id: str,
) -> dict[str, Any]:
    """
    Execute computational chemistry driver or delegate to Docker sandbox.

    :param script_name: Name of simulation script to run.
    :type script_name: str
    :param parameters: Optional input parameter dictionary.
    :type parameters: dict[str, Any] | None
    :param job_id: Unique job identifier string.
    :type job_id: str
    :return: Result dictionary containing status and output or error.
    :rtype: dict[str, Any]
    """
    params = parameters or {}
    pipeline_id, workspace_dir = _resolve_workspace_dir(params, job_id)
    scripts_repo = BASE_DIR / "scripts_repo" / "src"
    driver_path = scripts_repo / "afscripts" / "scripts" / "xtb_nanoreactor.py"

    if _is_nanoreactor_task(script_name, driver_path):
        return _run_nanoreactor_pipeline(
            workspace_dir, pipeline_id, job_id, params
        )

    chemistry_module = _is_chemistry_task(script_name)
    if chemistry_module:
        clean_key = script_name.replace(".py", "")
        return _run_chemistry_driver(
            clean_key,
            chemistry_module,
            workspace_dir,
            pipeline_id,
            job_id,
            params,
        )

    return run_docker_sandbox(script_name, params, job_id)


async def _mark_job_running_in_session(job_id: str) -> None:
    """
    Update database record marking the given job status to Running.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_running(job_id, session)


async def _handle_execution_success(
    job_id: str,
    output: Any,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> None:
    """
    Record job success and propagate DAG resolution to downstream jobs.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :param output: JSON output dictionary or simulation results.
    :type output: Any
    :param redis_client: Redis connection client for ARQ queueing.
    :type redis_client: Any
    :param duration_seconds: Elapsed simulation execution time.
    :type duration_seconds: float | None
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_success(
            job_id, output, session, duration_seconds=duration_seconds
        )
        await evaluate_downstream_dependencies(session, job_id, redis_client)


async def _handle_execution_failure(
    job_id: str,
    error_message: str,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> None:
    """
    Record job failure and propagate failure status to downstream dependencies.

    :param job_id: Unique job identifier string.
    :type job_id: str
    :param error_message: Reason or stack trace of the failure.
    :type error_message: str
    :param redis_client: Redis connection client for ARQ queueing.
    :type redis_client: Any
    :param duration_seconds: Elapsed execution duration before failure.
    :type duration_seconds: float | None
    :return: None
    :rtype: None
    """
    async with AsyncSessionLocal() as session:
        await mark_job_failed(
            job_id, error_message, session, duration_seconds=duration_seconds
        )
        await evaluate_downstream_dependencies(session, job_id, redis_client)


def _format_worker_exception(error_exc: Exception) -> str:
    """
    Format exception name and full traceback into string for error reporting.

    :param error_exc: Caught Python exception instance.
    :type error_exc: Exception
    :return: Formatted error trace string.
    :rtype: str
    """
    return f"{type(error_exc).__name__}: {error_exc}\n{traceback.format_exc()}"


async def _process_task_result(
    result: dict[str, Any],
    job_id: str,
    redis_client: Any,
    duration_seconds: float | None = None,
) -> Any:
    """
    Dispatch success or failure handling based on task execution result.

    :param result: Result mapping returned from run_script_task.
    :type result: dict[str, Any]
    :param job_id: Unique job identifier string.
    :type job_id: str
    :param redis_client: ARQ Redis connection pool.
    :type redis_client: Any
    :param duration_seconds: Elapsed simulation duration in seconds.
    :type duration_seconds: float | None
    :return: Simulation output payload on success.
    :rtype: Any
    :raises RuntimeError: If sandbox execution status is failed.
    """
    if result["status"] == "success":
        await _handle_execution_success(
            job_id, result["output"], redis_client, duration_seconds
        )
        return result["output"]

    error_msg = result["error"]
    await _handle_execution_failure(
        job_id, error_msg, redis_client, duration_seconds
    )
    raise RuntimeError(f"Sandbox execution failed: {error_msg}")


async def execute_script(
    worker_context: dict[str, Any],
    job_id: str,
    script_name: str,
    parameters: dict[str, Any] | None,
) -> Any:
    """
    Core ARQ worker entry point invoked upon dequeuing a simulation task.

    :param worker_context: ARQ task worker runtime context dictionary.
    :type worker_context: dict[str, Any]
    :param job_id: Target job identifier string.
    :type job_id: str
    :param script_name: Simulation script filename to execute.
    :type script_name: str
    :param parameters: Optional dictionary containing execution parameters.
    :type parameters: dict[str, Any] | None
    :return: Completed simulation output payload.
    :rtype: Any
    """
    params = parameters or {}
    redis_client = worker_context.get("redis")
    await _mark_job_running_in_session(job_id)

    event_loop = asyncio.get_event_loop()
    start_time = event_loop.time()
    try:
        result = await asyncio.to_thread(
            run_script_task, script_name, params, job_id
        )
        duration = round(event_loop.time() - start_time, 2)
        return await _process_task_result(
            result, job_id, redis_client, duration
        )
    except Exception as worker_exc:
        duration = round(event_loop.time() - start_time, 2)
        if not isinstance(worker_exc, RuntimeError):
            error_text = _format_worker_exception(worker_exc)
            await _handle_execution_failure(
                job_id, error_text, redis_client, duration
            )
        raise
