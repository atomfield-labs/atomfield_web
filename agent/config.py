"""
Agent settings, read from the environment.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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
        )
