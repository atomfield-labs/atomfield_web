"""
Agent settings: a settings file written by ``python -m agent login``
(``~/.config/atomfield/agent.toml``), with environment variables on
top. The environment wins, so a container (the house agent) can be
configured without any file.

The file looks like::

    api_url = "https://atomfield.example.org"
    token = "af_agent_..."
    runner = "slurm"
    work_folder = "/home/you/atomfield"
    python = "/home/you/atomfield/env/bin/python"
    ssh_address = "you@login.cluster.edu"
    max_jobs = 4

    [slurm]
    options = ["--account=my_project"]
    setup = ["module load quantum-espresso/7.2"]
    poll_seconds = 15.0

Jobs run the scripts release the server names, downloaded into the
work folder. ``pack_dir = "/path/to/afscripts/src"`` makes this agent
run its owner's own copy instead, for every job.
"""

import json
import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.slurm import SlurmSettings

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUE_WORDS = {"1", "true", "yes"}
CONFIG_PATH_VARIABLE = "ATOMFIELD_AGENT_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "atomfield" / "agent.toml"
STATE_FILE_NAME = "agent-state.json"
SLURM_TABLE = "slurm"
# Environment variable -> setting; the environment wins over the file.
ENVIRONMENT_SETTINGS = {
    "ATOMFIELD_API_URL": "api_url",
    "ATOMFIELD_AGENT_TOKEN": "token",
    "ATOMFIELD_RUNNER": "runner",
    "ATOMFIELD_MAX_JOBS": "max_jobs",
    "CHEMISTRY_PYTHON_BIN": "python",
    "ATOMFIELD_PACK_DIR": "pack_dir",
    "ARTIFACTS_DIR": "artifacts_dir",
    "ATOMFIELD_AGENT_STATE": "state_file",
    "ATOMFIELD_SSH_ADDRESS": "ssh_address",
    "ATOMFIELD_DELETE_AFTER_UPLOAD": "delete_after_upload",
}


class MissingSettingError(KeyError):
    """
    A required setting (API address, token) is nowhere to be found.
    """


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
    :param pack_source_dir: The owner's own copy of the scripts (the
        folder holding their packages), run instead of releases; None
        runs the release each job names.
    :type pack_source_dir: Path | None
    :param artifacts_dir: Root of all job workspaces.
    :type artifacts_dir: Path
    :param state_file: Where the agent remembers its jobs; its folder
        also holds the agent's log and locks.
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
    :param runner: ``process`` (jobs are the agent's children) or
        ``slurm`` (jobs go to the cluster's scheduler).
    :type runner: str
    :param slurm: How this cluster wants jobs submitted.
    :type slurm: SlurmSettings
    """

    api_url: str
    token: str
    max_jobs: int = 2
    python_bin: str = sys.executable
    pack_source_dir: Path | None = None
    artifacts_dir: Path = REPO_ROOT / "artifacts"
    state_file: Path = Path.home() / ".atomfield" / STATE_FILE_NAME
    heartbeat_seconds: float = 30.0
    claim_wait_seconds: float = 25.0
    ssh_address: str | None = None
    delete_after_upload: bool = False
    runner: str = "process"
    slurm: SlurmSettings = field(default_factory=SlurmSettings)

    @property
    def home(self) -> Path:
        """
        The agent's own folder: state file, log and locks.

        :return: The state file's folder.
        :rtype: Path
        """
        return self.state_file.parent

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "AgentConfig":
        """
        Read the settings file (if any), then apply the environment.

        :param path: Settings file; by default ``ATOMFIELD_AGENT_CONFIG``
            or ``~/.config/atomfield/agent.toml``.
        :type path: Path | None
        :param environ: Environment (the process's by default).
        :type environ: Mapping[str, str] | None
        :return: Agent configuration.
        :rtype: AgentConfig
        :raises MissingSettingError: If the API address or token is
            missing (run ``python -m agent login`` first).
        """
        environ = os.environ if environ is None else environ
        settings = read_settings(path or settings_path(environ))
        settings.update(
            {
                name: environ[variable]
                for variable, name in ENVIRONMENT_SETTINGS.items()
                if environ.get(variable)
            }
        )
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> "AgentConfig":
        """
        Build the configuration from flat settings (file keys).

        :param settings: Settings by name.
        :type settings: Mapping[str, Any]
        :return: Agent configuration.
        :rtype: AgentConfig
        :raises MissingSettingError: If the API address or token is
            missing.
        """
        for required in ("api_url", "token"):
            if not settings.get(required):
                raise MissingSettingError(
                    f"No {required} set: run 'python -m agent login' first"
                )
        defaults = cls(api_url="", token="")
        work = settings.get("work_folder")
        work_folder = Path(work).expanduser() if work else None
        artifacts = settings.get("artifacts_dir") or work_folder
        state = settings.get("state_file") or (
            work_folder / STATE_FILE_NAME if work_folder else None
        )
        return cls(
            api_url=str(settings["api_url"]).rstrip("/"),
            token=str(settings["token"]),
            max_jobs=int(settings.get("max_jobs", defaults.max_jobs)),
            python_bin=str(settings.get("python", defaults.python_bin)),
            pack_source_dir=optional_path(settings.get("pack_dir")),
            artifacts_dir=Path(
                artifacts or defaults.artifacts_dir
            ).expanduser(),
            state_file=Path(state or defaults.state_file).expanduser(),
            ssh_address=settings.get("ssh_address") or None,
            delete_after_upload=str(
                settings.get("delete_after_upload", "")
            ).lower()
            in TRUE_WORDS,
            runner=str(settings.get("runner", defaults.runner)),
            slurm=SlurmSettings(
                options=list(settings.get("slurm_options", [])),
                setup_lines=list(settings.get("slurm_setup", [])),
                poll_seconds=float(settings.get("slurm_poll_seconds", 15.0)),
            ),
        )


def optional_path(value: Any) -> Path | None:
    """
    A path setting that may be absent.

    :param value: The setting's value, if any.
    :type value: Any
    :return: The path (``~`` expanded), or None if not set.
    :rtype: Path | None
    """
    return Path(str(value)).expanduser() if value else None


def settings_path(environ: Mapping[str, str]) -> Path:
    """
    Where the settings file is.

    :param environ: Environment.
    :type environ: Mapping[str, str]
    :return: ``ATOMFIELD_AGENT_CONFIG`` or the default path.
    :rtype: Path
    """
    return Path(environ.get(CONFIG_PATH_VARIABLE) or DEFAULT_CONFIG_PATH)


def read_settings(path: Path) -> dict[str, Any]:
    """
    Read a settings file into flat settings; ``[slurm]`` keys become
    ``slurm_<key>``.

    :param path: Settings file.
    :type path: Path
    :return: Settings; empty if the file does not exist.
    :rtype: dict[str, Any]
    """
    if not path.is_file():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    slurm = data.pop(SLURM_TABLE, {})
    data.update({f"{SLURM_TABLE}_{key}": value for key, value in slurm.items()})
    return data


def toml_value(value: Any) -> str:
    """
    Write one value in TOML: strings and lists of strings as JSON
    (valid TOML for these), numbers and booleans as themselves.

    :param value: A string, number, boolean or list of strings.
    :type value: Any
    :return: TOML text.
    :rtype: str
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(
            json.dumps(item, ensure_ascii=False) for item in value
        )
        return f"[{items}]"
    return json.dumps(str(value), ensure_ascii=False)


def write_settings(path: Path, settings: Mapping[str, Any]) -> None:
    """
    Save flat settings as a TOML file readable only by its owner (it
    holds the agent's token).

    :param path: Settings file to write.
    :type path: Path
    :param settings: Settings; ``slurm_<key>`` go into ``[slurm]``.
    :type settings: Mapping[str, Any]
    """
    prefix = f"{SLURM_TABLE}_"
    plain = {
        key: value
        for key, value in settings.items()
        if not key.startswith(prefix) and value is not None
    }
    slurm = {
        key.removeprefix(prefix): value
        for key, value in settings.items()
        if key.startswith(prefix) and value is not None
    }
    lines = [f"{key} = {toml_value(value)}" for key, value in plain.items()]
    if slurm:
        lines += ["", f"[{SLURM_TABLE}]"]
        lines += [
            f"{key} = {toml_value(value)}" for key, value in slurm.items()
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    path.chmod(0o600)
