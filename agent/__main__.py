"""
Entry point: ``python -m agent [command]``.

- ``run`` (the default): run the agent in this terminal.
- ``login``: save this machine's settings and token.
- ``start``: run it in the background, restarted if it crashes, still
  running after you log out.
- ``stop``: stop it (Slurm jobs keep running; the next agent takes
  them over).
- ``status``: is it running, and what is it doing?
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from agent import daemon
from agent.agent import Agent
from agent.client import AgentClient
from agent.config import AgentConfig, MissingSettingError, settings_path
from agent.login import TokenRefusedError, login
from agent.runner import ProcessRunner, Runner
from agent.slurm import SlurmRunner
from agent.state import StateFile

EXIT_OK = 0
EXIT_FAILED = 1


def make_runner(config: AgentConfig) -> Runner:
    """
    The runner the settings ask for.

    :param config: Agent settings.
    :type config: AgentConfig
    :return: Slurm or local-process runner.
    :rtype: Runner
    """
    if config.runner == "slurm":
        return SlurmRunner(config.slurm)
    return ProcessRunner()


async def serve(config: AgentConfig) -> None:
    """
    Run an agent until SIGTERM or SIGINT.

    :param config: Agent settings.
    :type config: AgentConfig
    """
    client = AgentClient.connect(config.api_url, config.token)
    state = StateFile(config.state_file)
    agent = Agent(config, client, make_runner(config), state)
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, agent.request_stop)
    try:
        await agent.run()
    finally:
        await client.close()


def run_command(config: AgentConfig, path: Path) -> int:
    """
    Run the agent here, unless another one already runs for this work
    folder.

    :param config: Agent settings.
    :type config: AgentConfig
    :param path: Settings file (unused).
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        with daemon.exclusive(config.home / daemon.AGENT_LOCK):
            asyncio.run(serve(config))
    except daemon.AlreadyRunningError as running:
        print(f"Another agent already runs here (pid {running.pid}).")
        return EXIT_FAILED
    return EXIT_OK


def start_command(config: AgentConfig, path: Path) -> int:
    """
    Start the agent in the background.

    :param config: Agent settings.
    :type config: AgentConfig
    :param path: Settings file, passed on to the background agent.
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    try:
        pid = daemon.start(config, path)
    except daemon.AlreadyRunningError as running:
        print(f"The agent is already running (pid {running.pid}).")
        return EXIT_OK
    print(f"Agent started (pid {pid}); log: {config.home / daemon.LOG_NAME}")
    return EXIT_OK


def stop_command(config: AgentConfig, path: Path) -> int:
    """
    Stop the background agent.

    :param config: Agent settings.
    :type config: AgentConfig
    :param path: Settings file (unused).
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    stopped = daemon.stop(config)
    print("Agent stopped." if stopped else "The agent was not running.")
    return EXIT_OK


def status_command(config: AgentConfig, path: Path) -> int:
    """
    Print what the agent is doing.

    :param config: Agent settings.
    :type config: AgentConfig
    :param path: Settings file (unused).
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    print("\n".join(daemon.status(config)))
    return EXIT_OK


def supervise_command(config: AgentConfig, path: Path) -> int:
    """
    The background restart loop (started by ``start``).

    :param config: Agent settings.
    :type config: AgentConfig
    :param path: Settings file (unused).
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    try:
        daemon.supervise(config)
    except daemon.AlreadyRunningError:
        return EXIT_OK
    return EXIT_OK


COMMANDS = {
    "run": run_command,
    "start": start_command,
    "stop": stop_command,
    "status": status_command,
    "supervise": supervise_command,
}


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line.

    :return: Parser for ``python -m agent``.
    :rtype: argparse.ArgumentParser
    """
    # A subcommand's own default would overwrite a --config given
    # before it, so subcommands leave the value alone (SUPPRESS).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
        help="Settings file (default: ~/.config/atomfield/agent.toml)",
    )
    parser = argparse.ArgumentParser(
        prog="python -m agent",
        description="The AtomField agent: runs your jobs on this machine.",
    )
    parser.add_argument("--config", type=Path, default=None)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", parents=[common], help="Run in this terminal.")
    add_login_parser(commands, common)
    for name, text in (
        ("start", "Run in the background (survives logging out)."),
        ("stop", "Stop it; Slurm jobs keep running."),
        ("status", "Is it running, and what is it doing?"),
    ):
        commands.add_parser(name, parents=[common], help=text)
    commands.add_parser("supervise", parents=[common])
    return parser


def add_login_parser(commands, common: argparse.ArgumentParser) -> None:
    """
    Describe ``login``'s options; any left out are asked for.

    :param commands: The subcommand registry.
    :type commands: argparse._SubParsersAction
    :param common: Options every command takes.
    :type common: argparse.ArgumentParser
    """
    login_parser = commands.add_parser(
        "login", parents=[common], help="Save this machine's settings."
    )
    for flag in (
        "--api-url",
        "--token",
        "--work-folder",
        "--python",
        "--ssh-address",
    ):
        login_parser.add_argument(flag)
    login_parser.add_argument(
        "--pack-dir",
        help="Run your own copy of the scripts (folder holding afscripts) "
        "instead of the releases the server names",
    )
    login_parser.add_argument("--runner", choices=["slurm", "process"])
    login_parser.add_argument("--max-jobs", type=int)
    login_parser.add_argument(
        "--slurm-option", action="append", help="e.g. --account=x"
    )
    login_parser.add_argument(
        "--setup", action="append", help="Shell line run before each job"
    )
    login_parser.add_argument(
        "--yes", action="store_true", help="Ask nothing; use the defaults"
    )


def main(argv: list[str] | None = None) -> int:
    """
    Run one command.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Process exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    path = options.config or settings_path(os.environ)
    command = options.command or "run"
    try:
        if command == "login":
            print("\n".join(login(options, path)))
            return EXIT_OK
        config = AgentConfig.load(path)
        return COMMANDS[command](config, path)
    except (MissingSettingError, TokenRefusedError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
