"""
The agent's command line: the settings file, ``login``, and keeping
the agent alive in the background (``start``, ``status``, ``stop``)
with a supervisor that restarts it after a crash.
"""

import argparse
import os
import signal
import threading
import time
from pathlib import Path

import pytest

from agent import daemon
from agent.__main__ import main
from agent.config import (
    AGENT_COMMAND_VARIABLE,
    AgentConfig,
    MissingSettingError,
    agent_command,
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

        os.kill(first.pid, signal.SIGKILL)  # a crash, as far as it can tell
        second = wait_for(
            lambda: (
                (now := daemon.holder(agent_lock))
                and now.pid != first.pid
                and now
            ),
            "the restarted agent",
        )
        assert second.pid != first.pid
        assert not second.elsewhere
    finally:
        assert daemon.stop(config)
    assert daemon.holder(work / daemon.SUPERVISOR_LOCK) is None
    assert daemon.holder(agent_lock) is None
    assert "not running" in daemon.status(config)[0]


def test_a_restarted_agent_runs_the_copy_at_the_agent_path(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    The supervisor starts each agent in the agent's folder by path, so
    after ``agent.ship`` swaps the copy, a restart runs the new one
    (the folder the supervisor started in no longer exists).

    :param monkeypatch: Replaces starting a process.
    :type monkeypatch: pytest.MonkeyPatch
    """
    started = []
    stopping = threading.Event()

    class FinishedAgent:
        """
        An agent that ends at once, and asks the loop to stop.
        """

        def __init__(self, command: list[str], **options) -> None:
            """
            :param command: The command line.
            :type command: list[str]
            :param options: How it is started.
            :type options: Any
            """
            started.append(options)
            stopping.set()

        def wait(self) -> int:
            """
            :return: Its exit code.
            :rtype: int
            """
            return 0

    monkeypatch.setattr(daemon.subprocess, "Popen", FinishedAgent)
    daemon.keep_running(stopping, [])

    assert started == [{"cwd": daemon.REPO_ROOT}]


def test_settings_are_swapped_in_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    New settings are written beside the old file and swapped in, so a
    write stopped before the swap leaves the old file (and its token)
    as it was.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param monkeypatch: Stops the write at the swap.
    :type monkeypatch: pytest.MonkeyPatch
    """
    path = tmp_path / "agent.toml"
    write_settings(path, settings_for(tmp_path))
    before = path.read_text()

    def stopped(*args) -> None:
        """
        Ctrl+C just before the swap.

        :raises KeyboardInterrupt: Always.
        """
        raise KeyboardInterrupt

    monkeypatch.setattr("agent.config.os.replace", stopped)
    with pytest.raises(KeyboardInterrupt):
        write_settings(path, {"api_url": "http://new", "token": "t"})

    assert path.read_text() == before
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)


def test_messages_name_the_command_the_person_types():
    """
    Run through the shortcut, the agent suggests the shortcut (with ~
    for the home folder); run directly, ``python -m agent``.
    """
    shortcut = str(Path.home() / "atomfield" / "agent")

    assert agent_command({}) == "python -m agent"
    assert agent_command({AGENT_COMMAND_VARIABLE: shortcut}) == (
        "~/atomfield/agent"
    )


def config_in(tmp_path: Path) -> AgentConfig:
    """
    The settings of an agent working in ``tmp_path/atomfield``.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :return: The configuration.
    :rtype: AgentConfig
    """
    return AgentConfig.from_settings(settings_for(tmp_path / "atomfield"))


def lock_from_another_machine(path: Path, age_seconds: float) -> None:
    """
    Write a lock record as an agent on ``login9`` would, last renewed
    ``age_seconds`` ago.

    :param path: Lock file.
    :type path: Path
    :param age_seconds: Seconds since its last renewal.
    :type age_seconds: float
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("4242 login9")
    renewed = time.time() - age_seconds
    os.utime(path, (renewed, renewed))


def test_a_lock_names_its_holder_and_is_emptied_on_release(tmp_path: Path):
    """
    While held, the file says which process on which machine holds it;
    once released, it names nobody, for any machine.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    lock = tmp_path / "agent.lock"

    with daemon.exclusive(lock):
        named = lock.read_text()
        assert daemon.holder(lock) == daemon.LockHolder(
            os.getpid(), daemon.this_host()
        )

    assert named == f"{os.getpid()} {daemon.this_host()}"
    assert lock.read_text() == ""
    assert daemon.holder(lock) is None


def test_an_agent_on_another_login_node_is_respected_not_signalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    A lock another machine keeps renewing stops ``start`` here, makes
    ``status`` say where the agent runs, and makes ``stop`` refuse
    instead of signalling a process number that means nothing here.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param monkeypatch: Catches any signal sent.
    :type monkeypatch: pytest.MonkeyPatch
    """
    config = config_in(tmp_path)
    lock_from_another_machine(config.home / daemon.SUPERVISOR_LOCK, 5.0)

    def no_signals(pid: int, number: int) -> None:
        """
        :raises AssertionError: Always: nothing may be signalled.
        """
        raise AssertionError(f"signalled pid {pid}")

    monkeypatch.setattr(daemon.os, "kill", no_signals)

    with pytest.raises(daemon.AlreadyRunningError) as running:
        daemon.start(config, tmp_path / "agent.toml")
    assert running.value.holder == daemon.LockHolder(4242, "login9")
    assert "on login9 (pid 4242)" in daemon.status(config)[0]
    with pytest.raises(daemon.AlreadyRunningError):
        daemon.stop(config)


def test_a_lock_another_machine_stopped_renewing_frees_itself(
    tmp_path: Path,
):
    """
    Once another machine stops renewing its lock (its agent crashed, or
    the node went down), the lock counts as free; a record from before
    machines were recorded is left to this machine's file lock.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    lock = tmp_path / "supervisor.lock"
    lock_from_another_machine(lock, daemon.STALE_SECONDS + 60)
    assert daemon.holder(lock) is None

    lock.write_text("1234")
    assert daemon.holder(lock) is None


def test_every_does_its_chore_until_the_block_ends():
    """
    The background chore repeats while the block runs, and not after.
    """
    done = []

    with daemon.every(0.01, lambda: done.append(1)):
        time.sleep(0.15)
    count = len(done)
    time.sleep(0.05)

    assert count >= 3
    assert len(done) == count


def test_a_refused_token_ends_the_agent_with_its_own_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """
    ``run`` exits with ``EXIT_TOKEN_REFUSED`` and says what to do, and
    the supervisor does not restart it.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    :param monkeypatch: Makes the API refuse the token.
    :type monkeypatch: pytest.MonkeyPatch
    :param capsys: Captured output.
    :type capsys: pytest.CaptureFixture
    """
    path = tmp_path / "agent.toml"
    write_settings(path, settings_for(tmp_path / "atomfield"))

    async def refused(config: AgentConfig) -> None:
        """
        :raises TokenRefusedError: As the API's 401 does.
        """
        raise TokenRefusedError("The API refused this agent's token")

    monkeypatch.setattr("agent.__main__.serve", refused)
    code = main(["run", "--config", str(path)])
    assert code == daemon.EXIT_TOKEN_REFUSED
    assert "login" in capsys.readouterr().err

    starts = []

    class RefusedAgent:
        """
        An agent process that exits as a refused token makes it.
        """

        def __init__(self, command: list[str], **options) -> None:
            """
            :param command: The command line.
            :type command: list[str]
            :param options: How it is started.
            :type options: Any
            """
            starts.append(command)

        def wait(self) -> int:
            """
            :return: The refused-token exit code.
            :rtype: int
            """
            return daemon.EXIT_TOKEN_REFUSED

    monkeypatch.setattr(daemon.subprocess, "Popen", RefusedAgent)
    daemon.keep_running(threading.Event(), [])
    assert len(starts) == 1


def test_a_long_log_is_trimmed_and_writers_carry_on(tmp_path: Path):
    """
    Past its size the log moves to ``agent.log.1`` and starts again;
    a process appending to it carries on at the new end.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    log = tmp_path / "agent.log"
    with log.open("a") as writer:
        writer.write("old line\n" * 20)
        writer.flush()
        daemon.trim_log(log, max_bytes=100)
        writer.write("new line\n")
        writer.flush()

    assert log.read_text() == "new line\n"
    assert (tmp_path / "agent.log.1").read_text() == "old line\n" * 20
    daemon.trim_log(log, max_bytes=100)
    assert log.read_text() == "new line\n"
