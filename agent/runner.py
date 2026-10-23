"""
Runners start a task's command and stop it on demand.

``Runner`` and ``Execution`` are protocols: the agent depends only on
"start", "wait" and "terminate", so a Docker or Slurm runner can be
added later without touching the agent loop.
"""

import asyncio
import os
import signal
from pathlib import Path
from typing import Protocol

GRACE_SECONDS = 10.0


class Execution(Protocol):
    """
    One running command.
    """

    process_group: int

    async def wait(self) -> int:
        """
        Wait for the command to end.

        :return: Exit code.
        :rtype: int
        """

    async def terminate(self, grace_seconds: float = GRACE_SECONDS) -> None:
        """
        Stop the command and everything it started.

        :param grace_seconds: Time to exit cleanly before being killed.
        :type grace_seconds: float
        """


class Runner(Protocol):
    """
    Something that can start commands.
    """

    async def start(
        self,
        argv: list[str],
        workspace: Path,
        log_path: Path,
        environment: dict[str, str],
    ) -> Execution:
        """
        Start a command.

        :param argv: Command, as built by ``build_argv``.
        :type argv: list[str]
        :param workspace: Working directory.
        :type workspace: Path
        :param log_path: File for stdout and stderr.
        :type log_path: Path
        :param environment: Environment variables.
        :type environment: dict[str, str]
        :return: Handle to the running command.
        :rtype: Execution
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
    A command running as a local subprocess in its own process group.
    """

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

    async def wait(self) -> int:
        """
        Wait for the command to end.

        :return: Exit code.
        :rtype: int
        """
        return await self.process.wait()

    async def terminate(self, grace_seconds: float = GRACE_SECONDS) -> None:
        """
        Stop the command and every process it started (os.killpg), not
        just the top one, so no orphaned engine keeps burning CPU.

        :param grace_seconds: Time to exit cleanly before being killed.
        :type grace_seconds: float
        """
        await stop_group(self.process_group, grace_seconds)
        await self.process.wait()


class ProcessRunner:
    """
    Runs commands as local subprocesses.
    """

    async def start(
        self,
        argv: list[str],
        workspace: Path,
        log_path: Path,
        environment: dict[str, str],
    ) -> ProcessExecution:
        """
        Start a command in its own process group, logging all output.

        :param argv: Command, as built by ``build_argv``.
        :type argv: list[str]
        :param workspace: Working directory.
        :type workspace: Path
        :param log_path: File for stdout and stderr.
        :type log_path: Path
        :param environment: Environment variables.
        :type environment: dict[str, str]
        :return: Handle to the running command.
        :rtype: ProcessExecution
        """
        with log_path.open("w", encoding="utf-8") as log_stream:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace,
                stdout=log_stream,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        return ProcessExecution(process)
