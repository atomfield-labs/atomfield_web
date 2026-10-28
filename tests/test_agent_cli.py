"""
The agent's command line: the settings file, ``login``, and keeping
the agent alive in the background (``start``, ``status``, ``stop``)
with a supervisor that restarts it after a crash.
"""

import argparse
import os
import signal
import time
from pathlib import Path

import pytest

from agent import daemon
from agent.__main__ import main
from agent.config import (
    AgentConfig,
    MissingSettingError,
    read_settings,
    write_settings,
)
from agent.login import TokenRefusedError, login

# Nothing listens there: the agent keeps retrying, which is all the
# background tests need.
UNREACHABLE_API = "http://127.0.0.1:9"
WAIT_SECONDS = 20.0


def settings_for(work: Path) -> dict:
    """
    Settings of a cluster agent working in ``work``.

    :param work: Work folder.
    :type work: Path
    :return: Flat settings.
    :rtype: dict
    """
    return {
        "api_url": UNREACHABLE_API,
        "token": "af_agent_secret",
        "runner": "slurm",
        "work_folder": str(work),
        "slurm_options": ["--account=my_project"],
        "slurm_setup": ["module load quantum-espresso/7.2"],
    }


def login_options(**given) -> argparse.Namespace:
    """
    ``login`` arguments, as argparse would produce them.

    :param given: Options given on the command line.
    :type given: Any
    :return: Parsed options.
    :rtype: argparse.Namespace
    """
    names = [
        "api_url",
        "token",
        "runner",
        "work_folder",
        "python",
        "pack_dir",
        "ssh_address",
        "max_jobs",
        "slurm_option",
        "setup",
    ]
    values = dict.fromkeys(names) | {"yes": False} | given
    return argparse.Namespace(**values)


def wait_for(condition, what: str):
    """
    Poll until ``condition()`` is truthy.

    :param condition: Returns a value, or something falsy to wait.
    :type condition: Callable[[], Any]
    :param what: What is awaited, for the failure message.
    :type what: str
    :return: The first truthy value.
    :rtype: Any
    """
    give_up_at = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < give_up_at:
        if value := condition():
            return value
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def test_settings_survive_a_round_trip_and_the_environment_wins(
    tmp_path: Path,
):
    """
    The file gives the settings; an environment variable beats it;
    only its owner can read it, since it holds the token.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    path = tmp_path / "agent.toml"
    work = tmp_path / "atomfield"
    write_settings(path, settings_for(work))

    config = AgentConfig.load(path, environ={})
    assert (config.runner, config.artifacts_dir) == ("slurm", work)
    assert config.state_file == work / "agent-state.json"
    assert config.slurm.options == ["--account=my_project"]
    assert config.slurm.setup_lines == ["module load quantum-espresso/7.2"]
    assert path.stat().st_mode & 0o777 == 0o600

    other = AgentConfig.load(path, environ={"ATOMFIELD_API_URL": "http://x"})
    assert other.api_url == "http://x"


def test_without_settings_the_agent_says_to_log_in(tmp_path: Path):
    """
    No file and no environment: a clear message, not a stack trace.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    with pytest.raises(MissingSettingError, match="agent login"):
        AgentConfig.load(tmp_path / "none.toml", environ={})


def test_login_from_flags_checks_the_token_and_saves(tmp_path: Path):
    """
    With every answer given as a flag and ``--yes``, nothing is asked;
    the token is checked, then saved.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    path = tmp_path / "agent.toml"
    checked = []
    options = login_options(
        api_url="https://api.example.org",
        token="af_agent_secret",
        runner="slurm",
        work_folder=str(tmp_path / "atomfield"),
        slurm_option=["--account=my_project"],
        setup=["module load quantum-espresso/7.2"],
        yes=True,
    )

    lines = login(options, path, check=lambda *args: checked.append(args))

    assert checked == [("https://api.example.org", "af_agent_secret")]
    assert lines[0] == "The API accepted the token."
    saved = read_settings(path)
    assert saved["slurm_setup"] == ["module load quantum-espresso/7.2"]
    assert saved["token"] == "af_agent_secret"


def test_login_asks_for_what_is_missing(tmp_path: Path):
    """
    Questions for everything not given; the token is read without
    echo; Slurm questions only for a Slurm agent.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    answers = iter(
        [
            "https://api.example.org",  # API address
            "slurm",  # runner
            str(tmp_path / "atomfield"),  # work folder
            "",  # python: keep the default
            "you@login.hpc.edu",  # rsync address
            "--account=my_project --partition=standard",
            "module load quantum-espresso/7.2",
            "",  # no more setup lines
        ]
    )
    secrets = iter(["af_agent_secret"])
    path = tmp_path / "agent.toml"

    login(
        login_options(),
        path,
        ask=lambda question: next(answers),
        ask_secret=lambda question: next(secrets),
        check=lambda url, token: None,
    )

    config = AgentConfig.load(path, environ={})
    assert config.token == "af_agent_secret"
    assert config.ssh_address == "you@login.hpc.edu"
    assert config.slurm.options == [
        "--account=my_project",
        "--partition=standard",
    ]


def test_a_refused_token_is_not_saved(tmp_path: Path):
    """
    If the API does not know the token, nothing is written.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """

    def refuse(url, token):
        raise TokenRefusedError("The API does not recognise this token")

    path = tmp_path / "agent.toml"
    options = login_options(api_url="https://x", token="wrong", yes=True)
    with pytest.raises(TokenRefusedError):
        login(options, path, check=refuse)
    assert not path.exists()


def test_restarts_wait_longer_while_the_agent_keeps_crashing():
    """
    First restart soon; doubling while it crashes quickly; back to
    soon after a healthy run; never longer than the maximum.
    """
    first = daemon.next_delay(None, 0.1)
    assert first == daemon.RESTART_FIRST_SECONDS
    assert daemon.next_delay(first, 0.1) == 2 * first
    assert daemon.next_delay(first, daemon.HEALTHY_SECONDS) == first
    longest = daemon.next_delay(daemon.RESTART_MAX_SECONDS, 0.1)
    assert longest == daemon.RESTART_MAX_SECONDS


def test_a_second_agent_for_the_same_folder_is_refused(tmp_path: Path):
    """
    Two agents sharing one state file would take over each other's
    jobs, so ``run`` refuses while another holds the folder.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    path = tmp_path / "agent.toml"
    work = tmp_path / "atomfield"
    write_settings(path, settings_for(work))

    with daemon.exclusive(work / daemon.AGENT_LOCK):
        assert main(["run", "--config", str(path)]) == 1


def test_start_status_restart_and_stop_in_the_background(tmp_path: Path):
    """
    ``start`` detaches a supervisor that runs the agent; ``start``
    again is harmless; a killed agent comes back; ``stop`` ends both.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    path = tmp_path / "agent.toml"
    work = tmp_path / "atomfield"
    write_settings(path, {**settings_for(work), "runner": "process"})
    config = AgentConfig.load(path, environ={})
    agent_lock = work / daemon.AGENT_LOCK
    try:
        daemon.start(config, path)
        first = wait_for(lambda: daemon.holder(agent_lock), "the agent")
        assert "running" in daemon.status(config)[0]
        with pytest.raises(daemon.AlreadyRunningError):
            daemon.start(config, path)

        os.kill(first, signal.SIGKILL)  # a crash, as far as it can tell
        second = wait_for(
            lambda: (
                (pid := daemon.holder(agent_lock)) not in (None, first) and pid
            ),
            "the restarted agent",
        )
        assert second != first
    finally:
        assert daemon.stop(config)
    assert daemon.holder(work / daemon.SUPERVISOR_LOCK) is None
    assert daemon.holder(agent_lock) is None
    assert "not running" in daemon.status(config)[0]
