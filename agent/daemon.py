"""
Keep the agent running on a machine without tmux or cron (a cluster's
login node): ``start`` launches a detached supervisor that runs the
agent and restarts it if it crashes; ``stop`` and ``status`` find it
again through its lock files.

Two locks, both in the agent's folder:

- ``supervisor.lock``: one restart loop per folder (``start`` twice is
  harmless);
- ``agent.lock``: one agent per folder, even if someone also runs
  ``python -m agent run`` by hand. Two agents sharing one state file
  would take over each other's jobs.

A lock file names its holder (``<pid> <host>``) while it is held and
is emptied on release. A file lock is only sure within one machine
(a cluster's login nodes may not share them), so a long-running holder
also renews its file's time every ``REFRESH_SECONDS``; another machine
respects a record younger than ``STALE_SECONDS``, and never tries to
signal its process. A holder that crashed frees its lock: on its own
machine at once, elsewhere once the record goes stale.

The supervisor is started in a new session, so logging out (closing
the terminal) does not stop it. Nothing here survives a reboot of the
machine: then run ``python -m agent start`` again; Slurm kept the jobs
running and the new agent takes them over.
"""

import fcntl
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from types import FrameType
from typing import IO

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
REFRESH_SECONDS = 30.0
STALE_SECONDS = 180.0
# Past this size, agent.log moves to agent.log.1 and starts again.
LOG_MAX_BYTES = 10 * 1024 * 1024
# The agent's exit code when the API refuses its token: restarting
# cannot help, so the supervisor stops instead.
EXIT_TOKEN_REFUSED = 3


def this_host() -> str:
    """
    This machine's name, as lock files record it.

    :return: The host name.
    :rtype: str
    """
    return socket.gethostname()


@dataclass(frozen=True, slots=True)
class LockHolder:
    """
    Who holds a lock: a process on this machine or on another one.

    :param pid: Its process id, if known.
    :type pid: int | None
    :param host: Its machine; None in files written before machines
        were recorded (then it counts as this machine).
    :type host: str | None
    """

    pid: int | None
    host: str | None

    @property
    def elsewhere(self) -> bool:
        """
        Whether it runs on another machine (which this one can neither
        see nor signal).

        :return: True for another machine.
        :rtype: bool
        """
        return self.host is not None and self.host != this_host()

    def where(self) -> str:
        """
        Where it runs, for a person.

        :return: e.g. ``on login1 (pid 1234)`` or ``here (pid 1234)``.
        :rtype: str
        """
        place = f"on {self.host}" if self.elsewhere else "here"
        return f"{place} (pid {self.pid})"


class AlreadyRunningError(RuntimeError):
    """
    Another supervisor or agent already holds the lock.
    """

    def __init__(self, path: Path, holder: LockHolder) -> None:
        """
        :param path: The lock file.
        :type path: Path
        :param holder: Who holds it.
        :type holder: LockHolder
        """
        super().__init__(f"Already running {holder.where()} ({path.name})")
        self.holder = holder
        self.pid = holder.pid


def read_holder(path: Path) -> LockHolder | None:
    """
    The holder a lock file names, if any. Another machine's record
    counts only while that machine keeps renewing it.

    :param path: Lock file.
    :type path: Path
    :return: The named holder, or None.
    :rtype: LockHolder | None
    """
    try:
        words = path.read_text().split()
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if not words or not words[0].isdigit():
        return None
    named = LockHolder(int(words[0]), words[1] if len(words) > 1 else None)
    if named.elsewhere and age > STALE_SECONDS:
        return None
    return named


def refuse_if_held_elsewhere(path: Path) -> None:
    """
    Stop before touching a lock that a process on another machine
    still holds (its file lock may not reach this machine).

    :param path: Lock file.
    :type path: Path
    :raises AlreadyRunningError: If another machine holds it.
    """
    named = read_holder(path)
    if named is not None and named.elsewhere:
        raise AlreadyRunningError(path, named)


def rewrite(handle: IO[str], text: str) -> None:
    """
    Replace an open lock file's content.

    :param handle: The open file.
    :type handle: IO[str]
    :param text: New content.
    :type text: str
    """
    handle.seek(0)
    handle.truncate()
    handle.write(text)
    handle.flush()


@contextmanager
def exclusive(path: Path) -> Iterator[None]:
    """
    Hold a lock for the block, naming this process and machine in its
    file, which is emptied on release. The file lock dies with the
    process, so a crash never leaves a lock behind on this machine.

    :param path: Lock file.
    :type path: Path
    :return: Context manager.
    :rtype: Iterator[None]
    :raises AlreadyRunningError: If another process holds it, here or
        on another machine.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    refuse_if_held_elsewhere(path)
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        named = read_holder(path) or LockHolder(None, None)
        raise AlreadyRunningError(path, named) from None
    try:
        rewrite(handle, f"{os.getpid()} {this_host()}")
        yield
    finally:
        rewrite(handle, "")
        handle.close()


def holder(path: Path) -> LockHolder | None:
    """
    Who holds a lock now: a process here, a process on another machine
    that keeps renewing it, or nobody.

    :param path: Lock file.
    :type path: Path
    :return: The holder, or None if the lock is free.
    :rtype: LockHolder | None
    """
    if not path.exists():
        return None
    try:
        with exclusive(path):
            return None
    except AlreadyRunningError as running:
        return running.holder


@contextmanager
def every(seconds: float, chore: Callable[[], None]) -> Iterator[None]:
    """
    Do a chore every few seconds, in a background thread, for as long
    as the block runs.

    :param seconds: Time between two runs of the chore.
    :type seconds: float
    :param chore: What to do.
    :type chore: Callable[[], None]
    :return: Context manager.
    :rtype: Iterator[None]
    """
    done = threading.Event()
    thread = threading.Thread(
        target=repeat_until, args=(done, seconds, chore), daemon=True
    )
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()


def repeat_until(
    done: threading.Event, seconds: float, chore: Callable[[], None]
) -> None:
    """
    Do a chore every few seconds until ``done`` is set.

    :param done: Set when the chore is no longer wanted.
    :type done: threading.Event
    :param seconds: Time between two runs of the chore.
    :type seconds: float
    :param chore: What to do.
    :type chore: Callable[[], None]
    """
    while not done.wait(seconds):
        chore()


def renew(path: Path) -> None:
    """
    Show other machines that a lock's holder is alive: renew its
    file's time.

    :param path: Lock file.
    :type path: Path
    """
    with suppress(FileNotFoundError):
        os.utime(path)


@contextmanager
def held(path: Path) -> Iterator[None]:
    """
    Hold a lock for a long-running process, renewing it so that other
    machines sharing the folder see it is alive.

    :param path: Lock file.
    :type path: Path
    :return: Context manager.
    :rtype: Iterator[None]
    :raises AlreadyRunningError: If another process holds it.
    """
    with exclusive(path), every(REFRESH_SECONDS, partial(renew, path)):
        yield


def trim_log(log: Path, max_bytes: int = LOG_MAX_BYTES) -> None:
    """
    Keep the log under a size: past it, its content moves to
    ``agent.log.1`` (replacing the older one) and the log starts again
    empty. The supervisor and agent append to it, so they carry on at
    its new end (a line written between the copy and the emptying is
    lost).

    :param log: The log file.
    :type log: Path
    :param max_bytes: Size allowed before trimming.
    :type max_bytes: int
    """
    with suppress(FileNotFoundError):
        if log.stat().st_size > max_bytes:
            shutil.copyfile(log, log.with_name(f"{log.name}.1"))
            os.truncate(log, 0)


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


def refuse_if_running(home: Path) -> None:
    """
    Refuse to start a second agent for one folder: a supervisor, or an
    agent someone runs in a terminal, here or on another machine.

    :param home: The agent's folder.
    :type home: Path
    :raises AlreadyRunningError: If either lock is held.
    """
    for name in (SUPERVISOR_LOCK, AGENT_LOCK):
        running = holder(home / name)
        if running is not None:
            raise AlreadyRunningError(home / name, running)


def start(config: AgentConfig, config_path: Path) -> int:
    """
    Launch the supervisor, detached from this terminal.

    :param config: The agent's settings.
    :type config: AgentConfig
    :param config_path: Settings file, passed on to the supervisor.
    :type config_path: Path
    :return: The supervisor's pid.
    :rtype: int
    :raises AlreadyRunningError: If an agent already runs for this
        folder, here or on another machine.
    """
    refuse_if_running(config.home)
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
    SIGTERM (``stop``) or SIGINT, or until the API refuses its token.
    Meanwhile, keep the lock renewed and the log under its size.

    :param config: The agent's settings.
    :type config: AgentConfig
    :raises AlreadyRunningError: If another supervisor runs here.
    """
    stopping = threading.Event()
    current: list[subprocess.Popen] = []
    trim = partial(trim_log, config.home / LOG_NAME)
    with held(config.home / SUPERVISOR_LOCK), every(REFRESH_SECONDS, trim):
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

    def on_signal(signal_number: int, frame: FrameType | None) -> None:
        """
        Note the stop, and pass it on to the agent.

        :param signal_number: The signal (either means stop).
        :type signal_number: int
        :param frame: Where the supervisor was (unused).
        :type frame: FrameType | None
        """
        stopping.set()
        for child in current:
            child.terminate()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)


def run_agent_once(current: list[subprocess.Popen]) -> int:
    """
    Run ``python -m agent run`` until it exits.

    :param current: Filled with the agent process while it runs.
    :type current: list[subprocess.Popen]
    :return: Its exit code.
    :rtype: int
    """
    # By path: after agent.ship swaps the copy, the folder this
    # supervisor started in is gone, and a restart must find the new
    # one.
    child = subprocess.Popen(
        [sys.executable, "-m", "agent", "run"], cwd=REPO_ROOT
    )
    current[:] = [child]
    return child.wait()


def keep_running(
    stopping: threading.Event,
    current: list[subprocess.Popen],
) -> None:
    """
    Run the agent again and again until asked to stop, waiting longer
    between restarts while it keeps crashing. A refused token ends the
    loop: only a new token (``login``) can help.

    :param stopping: Set when a stop is requested.
    :type stopping: threading.Event
    :param current: Filled with the agent process now running.
    :type current: list[subprocess.Popen]
    """
    delay = None
    while not stopping.is_set():
        began = time.monotonic()
        code = run_agent_once(current)
        if code == EXIT_TOKEN_REFUSED:
            say("the API refused the agent's token; not restarting it")
            return
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
    :raises AlreadyRunningError: If it runs on another machine (it can
        only be stopped there).
    :raises TimeoutError: If it is still stopping after
        ``STOP_WAIT_SECONDS``.
    """
    lock = config.home / SUPERVISOR_LOCK
    running = holder(lock)
    if running is None:
        return False
    if running.elsewhere or running.pid is None:
        raise AlreadyRunningError(lock, running)
    with suppress(ProcessLookupError):
        os.kill(running.pid, signal.SIGTERM)
    give_up_at = time.monotonic() + STOP_WAIT_SECONDS
    while holder(lock) is not None:
        if time.monotonic() > give_up_at:
            raise TimeoutError(f"Still stopping {running.where()}")
        time.sleep(0.2)
    return True


def running_state(
    supervisor: LockHolder | None, agent: LockHolder | None
) -> str:
    """
    What ``status`` says about the agent's processes.

    :param supervisor: Holder of the supervisor's lock.
    :type supervisor: LockHolder | None
    :param agent: Holder of the agent's lock.
    :type agent: LockHolder | None
    :return: One line.
    :rtype: str
    """
    if supervisor is None and agent is None:
        return "not running"
    if supervisor is None:
        return f"running in a terminal {agent.where()}, without restarts"
    if supervisor.elsewhere:
        return f"running {supervisor.where()}; log in there to stop it"
    agent_pid = agent.pid if agent else None
    return f"running (supervisor pid {supervisor.pid}, agent pid {agent_pid})"


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
    jobs = len(StateFile(config.state_file).load())
    own_copy = config.pack_source_dir
    scripts = f"your own copy, {own_copy}" if own_copy else "releases"
    return [
        f"Agent:   {running_state(supervisor, agent)}",
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
