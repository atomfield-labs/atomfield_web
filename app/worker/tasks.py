"""
app/worker/tasks.py — ARQ Background Tasks

📚 LESSON: The Worker Process (Phase 3: Secure Docker Sandbox)

    We have offloaded execution from the current Python process to a fully
    isolated, ephemeral Docker container. 

    Constraints applied:
    • asyncio.to_thread: `docker-py` is synchronous. If we didn't offload it
      to a thread, a 5-hour simulation would block the ARQ event loop, 
      causing it to drop heartbeat and appear dead.
    • Secure Sandboxing: network_disabled, mem_limit, and read-only mounts
      prevent malicious scripts from breaking out or causing OOMs.
"""

import asyncio
import json
import os
import traceback
from typing import Dict, Any

import docker
from docker.errors import ContainerError, ImageNotFound

from app.db.session import AsyncSessionLocal
from app.services.job_service import mark_job_running, mark_job_success, mark_job_failed, evaluate_downstream_dependencies

# Initialize the Docker Client
docker_client = docker.from_env()

# Define the absolute path to the scripts directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# For Docker-out-of-Docker sandboxing, we need the path on the host, not the container
HOST_SCRIPTS_DIR = os.getenv("HOST_SCRIPTS_DIR")
HOST_ARTIFACTS_DIR = os.getenv("HOST_ARTIFACTS_DIR")

if not HOST_SCRIPTS_DIR or not HOST_ARTIFACTS_DIR:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    HOST_SCRIPTS_DIR = HOST_SCRIPTS_DIR or os.path.join(BASE_DIR, "scripts")
    HOST_ARTIFACTS_DIR = HOST_ARTIFACTS_DIR or os.path.join(BASE_DIR, "artifacts")

def run_docker_sandbox(script_name: str, parameters: dict, job_id: str) -> Dict[str, Any]:
    """
    Synchronous function that spins up an isolated container and captures output.
    MUST be run in a separate thread.
    """
    try:
        env_vars = {"JOB_PARAMS": json.dumps(parameters)}
        
        # Determine the workspace ID. If part of a DAG, it should share a pipeline_id.
        # Fallback to job_id for standalone script executions.
        pipeline_id = parameters.get("pipeline_id", f"job_{job_id}")
        
        # Create the physical folder on the host
        workspace_host_path = os.path.join(HOST_ARTIFACTS_DIR, pipeline_id)
        os.makedirs(workspace_host_path, exist_ok=True)
        
        # Pull image if not exists (fail-safe)
        try:
            docker_client.images.get("python:3.11-slim")
        except ImageNotFound:
            docker_client.images.pull("python:3.11-slim")
        
        # Enterprise Sandbox Execution
        # We capture stdout/stderr via the run() method
        logs = docker_client.containers.run(
            image="python:3.11-slim",
            command=["python", f"/sandbox/{script_name}"],
            volumes={
                HOST_SCRIPTS_DIR: {'bind': '/sandbox', 'mode': 'ro'},
                workspace_host_path: {'bind': '/workspace', 'mode': 'rw'}
            },
            environment=env_vars,
            remove=True,
            network_disabled=True,
            mem_limit="512m",
            stderr=True,
            stdout=True
        )
        
        # The script contract dictates it must print JSON to stdout
        raw_output = logs.decode('utf-8').strip()
        
        # Handle cases where the script output isn't valid JSON (e.g. syntax error in script)
        try:
            output_data = json.loads(raw_output)
            return {"status": "success", "output": output_data}
        except json.JSONDecodeError:
            return {"status": "failed", "error": f"Output was not valid JSON. Raw output: {raw_output}"}
            
    except ContainerError as e:
        # Container exited with non-zero code
        return {"status": "failed", "error": f"Container execution failed: {e.stderr.decode('utf-8')}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

async def execute_script(ctx, job_id: str, script_name: str, parameters: dict):
    """
    The core worker task — ARQ calls this when it dequeues a job.
    """
    print(f"[ATOMFIELD WORKER] ▶ Booting Sandbox for Job {job_id} → {script_name}")
    print(f"[ATOMFIELD WORKER]   Parameters: {parameters}")

    # --- Phase A: Mark as Running ---
    async with AsyncSessionLocal() as session:
        await mark_job_running(job_id, session)

    try:
        # Offload the blocking Docker process to a background thread
        result = await asyncio.to_thread(run_docker_sandbox, script_name, parameters, job_id)

        # --- Phase B: Terminal State Update ---
        async with AsyncSessionLocal() as session:
            if result["status"] == "success":
                await mark_job_success(job_id, result["output"], session)
                print(f"[ATOMFIELD WORKER] ✓ Finished Job {job_id}")
                
                # CRITICAL: Trigger the DAG evaluation callback
                await evaluate_downstream_dependencies(session, job_id, ctx['redis'])
                
                return result["output"]
            else:
                # Docker sandbox encountered an error (e.g., bad script, invalid JSON output)
                error_msg = result["error"]
                await mark_job_failed(job_id, error_msg, session)
                print(f"[ATOMFIELD WORKER] ✗ Failed Job {job_id} (Sandbox Error): {error_msg}")
                raise RuntimeError(f"Sandbox execution failed: {error_msg}")

    except Exception as exc:
        # --- Phase B (alternate): Mark as Failed (Worker Level Exception) ---
        # Catch unexpected worker-level exceptions (e.g. DB connection dropped during execution)
        if not isinstance(exc, RuntimeError):  # Avoid re-logging sandbox errors
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            print(f"[ATOMFIELD WORKER] ✗ Failed Job {job_id} (Worker Exception): {exc}")

            async with AsyncSessionLocal() as session:
                await mark_job_failed(job_id, error_msg, session)

        raise  # Re-raise so ARQ marks the job as failed in its own tracking
