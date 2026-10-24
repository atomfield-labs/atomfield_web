"""
Agent settings, read from the environment.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUE_WORDS = {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """
    Everything the agent needs to know about its server and machine.

    :param api_url: Base URL of the API, e.g. ``http://localhost:8000``.
    :type api_url: str
    :param token: The agent's bearer token.
    :type token: str
    :param max_jobs: Jobs run at the same time.
    :type max_jobs: int
    :param python_bin: Interpreter of the domain pack's environment.
    :type python_bin: str
    :param pack_source_dir: Directory holding the pack's packages.
    :type pack_source_dir: Path
    :param artifacts_dir: Root of all job workspaces.
    :type artifacts_dir: Path
    :param state_file: Where the agent remembers its processes.
    :type state_file: Path
    :param heartbeat_seconds: Time between heartbeats.
    :type heartbeat_seconds: float
    :param claim_wait_seconds: Long-poll wait per claim.
    :type claim_wait_seconds: float
    :param ssh_address: What a user types before ':' to rsync results
        from this machine (``you@login.hpc.edu``); None where results
        are local (a laptop) or uploaded (the house agent).
    :type ssh_address: str | None
    :param delete_after_upload: Remove a run's folder once its zip is
        uploaded (the house agent: our disk, not the user's).
    :type delete_after_upload: bool
    """

    api_url: str
    token: str
    max_jobs: int = 2
    python_bin: str = sys.executable
    pack_source_dir: Path = REPO_ROOT / "scripts_repo" / "src"
    artifacts_dir: Path = REPO_ROOT / "artifacts"
    state_file: Path = Path.home() / ".atomfield" / "agent-state.json"
    heartbeat_seconds: float = 30.0
    claim_wait_seconds: float = 25.0
    ssh_address: str | None = None
    delete_after_upload: bool = False

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        """
        Build the configuration from ``ATOMFIELD_*`` variables.

        :return: Agent configuration.
        :rtype: AgentConfig
        :raises KeyError: If the API URL or token is missing.
        """
        defaults = cls(api_url="", token="")
        environ = os.environ
        return cls(
            api_url=environ["ATOMFIELD_API_URL"].rstrip("/"),
            token=environ["ATOMFIELD_AGENT_TOKEN"],
            max_jobs=int(environ.get("ATOMFIELD_MAX_JOBS", defaults.max_jobs)),
            python_bin=environ.get("CHEMISTRY_PYTHON_BIN", defaults.python_bin),
            pack_source_dir=Path(
                environ.get("ATOMFIELD_PACK_DIR", defaults.pack_source_dir)
            ),
            artifacts_dir=Path(
                environ.get("ARTIFACTS_DIR", defaults.artifacts_dir)
            ),
            state_file=Path(
                environ.get("ATOMFIELD_AGENT_STATE", defaults.state_file)
            ),
            ssh_address=environ.get("ATOMFIELD_SSH_ADDRESS") or None,
            delete_after_upload=environ.get(
                "ATOMFIELD_DELETE_AFTER_UPLOAD", ""
            ).lower()
            in TRUE_WORDS,
        )
