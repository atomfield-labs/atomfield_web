"""
Keep the agent running on a machine without tmux or cron (a cluster's
login node): ``start`` launches a detached supervisor that runs the
agent and restarts it if it crashes; ``stop`` and ``status`` find it
again through its lock files.

Two locks, both in the agent's folder, each holding its owner's pid:

- ``supervisor.lock``: one restart loop per folder (``start`` twice is
  harmless);
- ``agent.lock``: one agent per folder, even if someone also runs
  ``python -m agent run`` by hand. Two agents sharing one state file
  would take over each other's jobs.

The supervisor is started in a new session, so logging out (closing
the terminal) does not stop it. Nothing here survives a reboot of the
machine: then run ``python -m agent start`` again; Slurm kept the jobs
running and the new agent takes them over.
"""

import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from agent.config import CONFIG_PATH_VARIABLE, REPO_ROOT, AgentConfig
from agent.state import StateFile

SUPERVISOR_LOCK = "supervisor.lock"
AGENT_LOCK = "agent.lock"
LOG_NAME = "agent.log"
# Restart quickly after a crash, slower after repeated crashes; a run
# this long counts as healthy and resets the wait.
RESTART_FIRST_SECONDS = 2.0
RESTART_MAX_SECONDS = 300.0
HEALTHY_SECONDS = 600.0
STOP_WAIT_SECONDS = 60.0
LOG_TAIL_LINES = 10


class AlreadyRunningError(RuntimeError):
    """
    Another supervisor or agent already holds the lock.
    """

    def __init__(self, path: Path, pid: int | None) -> None:
        """
        :param path: The lock file.
        :type path: Path
        :param pid: Its holder, if known.
        :type pid: int | None
        """
        super().__init__(f"Already running (pid {pid}, {path.name})")
        self.pid = pid


def read_pid(path: Path) -> int | None:
    """
    The pid written in a lock file.

    :param path: Lock file.
    :type path: Path
    :return: Pid, or None if absent or unreadable.
    :rtype: int | None
    """
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


@contextmanager
def exclusive(path: Path) -> Iterator[None]:
    """
    Hold an exclusive lock on a file for the block, writing our pid in
    it. The lock dies with the process, so a crash never leaves a
    stale lock behind.

    :param path: Lock file.
    :type path: Path
    :return: Context manager.
    :rtype: Iterator[None]
    :raises AlreadyRunningError: If another process holds it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise AlreadyRunningError(path, read_pid(path)) from None
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        handle.close()


def holder(path: Path) -> int | None:
    """
    Who holds a lock now.

    :param path: Lock file.
    :type path: Path
    :return: The holder's pid, or None if the lock is free.
    :rtype: int | None
    """
    if not path.exists():
        return None
    try:
        with exclusive(path):
            return None
    except AlreadyRunningError as running:
        return running.pid or -1


def next_delay(previous: float | None, ran_seconds: float) -> float:
    """
    How long to wait before restarting a crashed agent: short at first
    or after a healthy run, doubling while it keeps crashing.

    :param previous: The last wait, or None before any restart.
    :type previous: float | None
    :param ran_seconds: How long the agent ran before it stopped.
    :type ran_seconds: float
    :return: Seconds to wait.
    :rtype: float
    """
    if previous is None or ran_seconds >= HEALTHY_SECONDS:
        return RESTART_FIRST_SECONDS
    return min(previous * 2, RESTART_MAX_SECONDS)


def say(message: str) -> None:
    """
    Write a timestamped line to the supervisor's log (its stdout).

    :param message: What happened.
    :type message: str
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} supervisor: {message}", flush=True)


def start(config: AgentConfig, config_path: Path) -> int:
    """
    Launch the supervisor, detached from this terminal.

    :param config: The agent's settings.
    :type config: AgentConfig
    :param config_path: Settings file, passed on to the supervisor.
    :type config_path: Path
    :return: The supervisor's pid.
    :rtype: int
    :raises AlreadyRunningError: If a supervisor is already running.
    """
    lock = config.home / SUPERVISOR_LOCK
    running = holder(lock)
    if running is not None:
        raise AlreadyRunningError(lock, running)
    config.home.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, CONFIG_PATH_VARIABLE: str(config_path)}
    with (config.home / LOG_NAME).open("a") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "agent", "supervise"],
            cwd=REPO_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process.pid


def supervise(config: AgentConfig) -> None:
    """
    Run the agent, restarting it whenever it stops unasked, until
    SIGTERM (``stop``) or SIGINT.

    :param config: The agent's settings.
    :type config: AgentConfig
    :raises AlreadyRunningError: If another supervisor runs here.
    """
    stopping = threading.Event()
    current: list[subprocess.Popen] = []
    with exclusive(config.home / SUPERVISOR_LOCK):
        install_stop_handlers(stopping, current)
        say(f"started (pid {os.getpid()})")
        keep_running(stopping, current)
        say("stopped")


def install_stop_handlers(
    stopping: threading.Event,
    current: list[subprocess.Popen],
) -> None:
    """
    On SIGTERM or SIGINT: stop restarting, and ask the running agent
    to stop gracefully (it forwards nothing to Slurm jobs).

    :param stopping: Set when a stop is requested.
    :type stopping: threading.Event
    :param current: The agent process now running (zero or one).
    :type current: list[subprocess.Popen]
    """

    def on_signal(signal_number: int, frame) -> None:
        stopping.set()
        for child in current:
            child.terminate()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)


def keep_running(
    stopping: threading.Event,
    current: list[subprocess.Popen],
) -> None:
    """
    Run ``python -m agent run`` again and again until asked to stop,
    waiting longer between restarts while it keeps crashing.

    :param stopping: Set when a stop is requested.
    :type stopping: threading.Event
    :param current: Filled with the agent process now running.
    :type current: list[subprocess.Popen]
    """
    delay = None
    while not stopping.is_set():
        began = time.monotonic()
        child = subprocess.Popen([sys.executable, "-m", "agent", "run"])
        current[:] = [child]
        code = child.wait()
        if stopping.is_set():
            return
        delay = next_delay(delay, time.monotonic() - began)
        say(f"agent exited with code {code}; restart in {delay:.0f} s")
        stopping.wait(delay)


def stop(config: AgentConfig) -> bool:
    """
    Stop the supervisor and its agent. Slurm jobs keep running; the
    next agent takes them over.

    :param config: The agent's settings.
    :type config: AgentConfig
    :return: False if nothing was running.
    :rtype: bool
    """
    lock = config.home / SUPERVISOR_LOCK
    pid = holder(lock)
    if pid is None:
        return False
    os.kill(pid, signal.SIGTERM)
    give_up_at = time.monotonic() + STOP_WAIT_SECONDS
    while holder(lock) is not None and time.monotonic() < give_up_at:
        time.sleep(0.2)
    return True


def status(config: AgentConfig) -> list[str]:
    """
    Describe the agent on this machine, for ``python -m agent status``.

    :param config: The agent's settings.
    :type config: AgentConfig
    :return: Lines to print.
    :rtype: list[str]
    """
    supervisor = holder(config.home / SUPERVISOR_LOCK)
    agent = holder(config.home / AGENT_LOCK)
    state = (
        f"running (supervisor pid {supervisor}, agent pid {agent})"
        if supervisor
        else "not running"
    )
    jobs = len(StateFile(config.state_file).load())
    own_copy = config.pack_source_dir
    scripts = f"your own copy, {own_copy}" if own_copy else "releases"
    return [
        f"Agent:   {state}",
        f"API:     {config.api_url}",
        f"Runs on: {config.runner}, work folder {config.artifacts_dir}",
        f"Scripts: {scripts}",
        f"Jobs:    {jobs} in progress",
        *log_tail(config.home / LOG_NAME),
    ]


def log_tail(log: Path) -> list[str]:
    """
    The last lines of the agent's log, with a heading.

    :param log: Log file.
    :type log: Path
    :return: Lines; none if there is no log yet.
    :rtype: list[str]
    """
    if not log.is_file():
        return []
    tail = log.read_text(errors="ignore").splitlines()[-LOG_TAIL_LINES:]
    return [f"Log:     {log} (last lines)", *tail]
