"""
Runners start a job's command and stop it on demand.

``Runner`` and ``Execution`` are protocols, so the agent loop does not
care how a job runs. Two runners exist:

- ``ProcessRunner``: the job is the agent's own child process (a
  laptop, our server). It starts at once, the agent times it, and it
  dies with the agent.
- ``SlurmRunner`` (``agent.slurm``): the job is handed to a cluster's
  scheduler. It may wait in the scheduler's queue, the scheduler
  enforces its time limit, and it keeps running if the agent stops,
  so a restarted agent adopts it. ``Runner.scheduled`` says which kind
  of runner the agent has.
"""

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.catalog.models import Resources

GRACE_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class Command:
    """
    One job's command and what it needs to run.

    :param argv: Command, as built by ``build_argv``.
    :type argv: list[str]
    :param workspace: The job's folder (its working directory).
    :type workspace: Path
    :param log_path: File for stdout and stderr.
    :type log_path: Path
    :param environment: Variables to add to the environment (only the
        additions: a batch script must not copy the login node's).
    :type environment: dict[str, str]
    :param name: Short name, shown by schedulers (``af-<node>``).
    :type name: str
    :param resources: CPUs, memory and time limit from the catalog.
    :type resources: Resources
    """

    argv: list[str]
    workspace: Path
    log_path: Path
    environment: dict[str, str]
    name: str
    resources: Resources


class Execution(Protocol):
    """
    One running (or queued) job.
    """

    #: How the runner finds the job again: a process group, a Slurm id.
    handle: str
    #: The job has begun running (not just waiting in a queue).
    started: bool
    #: The scheduler stopped the job at its time limit.
    timed_out: bool

    async def wait(self) -> int:
        """
        Wait for the job to end.

        :return: Exit code.
        :rtype: int
        """

    async def terminate(self, grace_seconds: float = GRACE_SECONDS) -> None:
        """
        Stop the job and everything it started.

        :param grace_seconds: Time to exit cleanly before being killed.
        :type grace_seconds: float
        """


class Runner(Protocol):
    """
    Something that can start jobs.
    """

    #: Jobs belong to a scheduler, not to the agent: they may queue,
    #: the scheduler times them, and they outlive the agent.
    scheduled: bool

    async def start(self, command: Command) -> Execution:
        """
        Start (or submit) a job.

        :param command: What to run and with what resources.
        :type command: Command
        :return: Handle to the job.
        :rtype: Execution
        """

    async def adopt(self, handle: str, workspace: Path) -> Execution | None:
        """
        Deal with a job a previous agent started: take it over, or stop
        it if it cannot be taken over.

        :param handle: The job's handle, from the state file.
        :type handle: str
        :param workspace: The job's folder.
        :type workspace: Path
        :return: The job to keep watching, or None if it was stopped.
        :rtype: Execution | None
        """

    async def close(self) -> None:
        """
        Stop any background work (a scheduler watcher) on shutdown.
        Jobs are not touched.
        """


def signal_group(process_group: int, signal_number: int) -> bool:
    """
    Send a signal to a whole process group.

    :param process_group: Group id (the leader's pid).
    :type process_group: int
    :param signal_number: Signal to send.
    :type signal_number: int
    :return: False if the group no longer exists.
    :rtype: bool
    """
    try:
        os.killpg(process_group, signal_number)
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS answers EPERM for a group whose only members are zombies
        # (exited, exit status not yet collected): nothing left to stop.
        return False
    return True


def group_is_alive(process_group: int) -> bool:
    """
    Check whether any process of a group is still running.

    :param process_group: Group id.
    :type process_group: int
    :return: True while at least one member exists.
    :rtype: bool
    """
    return signal_group(process_group, 0)


async def stop_group(
    process_group: int,
    grace_seconds: float = GRACE_SECONDS,
) -> None:
    """
    SIGTERM a process group, then SIGKILL whatever is left.

    Works for groups this process did not start (orphans of a crashed
    agent), which is why it polls instead of waiting on a child.

    :param process_group: Group id.
    :type process_group: int
    :param grace_seconds: Time to exit cleanly before being killed.
    :type grace_seconds: float
    """
    if not signal_group(process_group, signal.SIGTERM):
        return
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + grace_seconds
    while group_is_alive(process_group) and loop.time() < give_up_at:
        await asyncio.sleep(0.1)
    signal_group(process_group, signal.SIGKILL)


class ProcessExecution:
    """
    A job running as a local subprocess in its own process group.
    """

    # A child process runs at once, and the agent itself times it.
    started = True
    timed_out = False

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        """
        Wrap a started subprocess.

        :param process: Subprocess started in a new session.
        :type process: asyncio.subprocess.Process
        """
        self.process = process
        # start_new_session makes the child the leader of a new group,
        # so its group id is its pid.
        self.process_group = process.pid
        self.handle = str(process.pid)

    async def wait(self) -> int:
        """
        Wait for the job to end.

        :return: Exit code.
        :rtype: int
        """
        return await self.process.wait()

    async def terminate(self, grace_seconds: float = GRACE_SECONDS) -> None:
        """
        Stop the job and every process it started (os.killpg), not
        just the top one, so no orphaned engine keeps burning CPU.

        :param grace_seconds: Time to exit cleanly before being killed.
        :type grace_seconds: float
        """
        await stop_group(self.process_group, grace_seconds)
        await self.process.wait()


class ProcessRunner:
    """
    Runs jobs as local subprocesses.
    """

    scheduled = False

    async def start(self, command: Command) -> ProcessExecution:
        """
        Start a job in its own process group, logging all output.

        :param command: What to run.
        :type command: Command
        :return: Handle to the running job.
        :rtype: ProcessExecution
        """
        environment = {**os.environ, **command.environment}
        with command.log_path.open("w", encoding="utf-8") as log_stream:
            process = await asyncio.create_subprocess_exec(
                *command.argv,
                cwd=command.workspace,
                stdout=log_stream,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        return ProcessExecution(process)

    async def adopt(self, handle: str, workspace: Path) -> None:
        """
        Stop a job a crashed agent left running. Its results cannot be
        trusted or collected (its parent is gone); the server retries
        the job once its lease expires.

        :param handle: The orphan's process group.
        :type handle: str
        :param workspace: The job's folder (unused).
        :type workspace: Path
        """
        await stop_group(int(handle))

    async def close(self) -> None:
        """
        Nothing runs in the background.
        """
