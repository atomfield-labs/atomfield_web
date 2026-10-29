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
from agent.client import AgentClient, TokenRefusedError
from agent.config import (
    AgentConfig,
    MissingSettingError,
    RunnerKind,
    agent_command,
    settings_path,
)
from agent.login import login
from agent.runner import ProcessRunner, Runner
from agent.slurm import SlurmRunner
from agent.state import StateFile
from app.core.cli import EXIT_FAILED, EXIT_OK, fail, stops_cleanly

DESCRIPTION = "The AtomField agent: runs your jobs on this machine."
CONFIG_HELP = "Settings file (default: ~/.config/atomfield/agent.toml)"
# Commands besides login, and what each does.
COMMAND_HELP = {
    "run": "Run in this terminal.",
    "start": "Run in the background (survives logging out).",
    "stop": "Stop it; Slurm jobs keep running.",
    "status": "Is it running, and what is it doing?",
}
# login's options; any left out are asked for.
LOGIN_OPTIONS: dict[str, dict] = {
    "--api-url": {},
    "--token": {},
    "--work-folder": {},
    "--python": {},
    "--ssh-address": {},
    "--pack-dir": {
        "help": "Run your own copy of the scripts (folder holding "
        "afscripts) instead of the releases the server names"
    },
    "--runner": {"choices": list(RunnerKind)},
    "--max-jobs": {"type": int},
    "--slurm-option": {"action": "append", "help": "e.g. --account=x"},
    "--setup": {"action": "append", "help": "Shell line run before each job"},
    "--yes": {"action": "store_true", "help": "Ask nothing; use the defaults"},
}
REFUSED_TOKEN_HELP = (
    "The API refused this agent's token: the cluster was removed in the "
    "web app, or its token was replaced. Make a new token there, then "
    "run '{command} login' and '{command} start'."
)


def already_running(holder: daemon.LockHolder) -> str:
    """
    Where the agent already runs, and, if that is another machine,
    that it is managed there.

    :param holder: The lock's holder.
    :type holder: daemon.LockHolder
    :return: One line for the person.
    :rtype: str
    """
    if holder.elsewhere:
        return (
            f"The agent runs {holder.where()}; log in there to manage it "
            f"(ssh {holder.host})."
        )
    return f"The agent is already running {holder.where()}."


def make_runner(config: AgentConfig) -> Runner:
    """
    The runner the settings ask for.

    :param config: Agent settings.
    :type config: AgentConfig
    :return: Slurm or local-process runner.
    :rtype: Runner
    """
    if config.runner == RunnerKind.SLURM:
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
        with daemon.held(config.home / daemon.AGENT_LOCK):
            asyncio.run(serve(config))
    except daemon.AlreadyRunningError as running:
        where = running.holder.where()
        print(f"Another agent already runs for this folder {where}.")
        return EXIT_FAILED
    except TokenRefusedError:
        print(refused_token_help(), file=sys.stderr)
        return daemon.EXIT_TOKEN_REFUSED
    return EXIT_OK


def refused_token_help() -> str:
    """
    What to do when the API refuses the agent's token.

    :return: One paragraph, naming the command the person types.
    :rtype: str
    """
    return REFUSED_TOKEN_HELP.format(command=agent_command(os.environ))


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
        print(already_running(running.holder))
        return EXIT_FAILED if running.holder.elsewhere else EXIT_OK
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
    try:
        stopped = daemon.stop(config)
    except daemon.AlreadyRunningError as running:
        print(already_running(running.holder))
        return EXIT_FAILED
    except TimeoutError as error:
        print(f"{error}; check again with: {agent_command(os.environ)} status")
        return EXIT_FAILED
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


@stops_cleanly("Login stopped; nothing was saved.")
def login_command(options: argparse.Namespace, path: Path) -> int:
    """
    Ask for, check and save this machine's settings. The file is
    written only at the end, so stopping half-way changes nothing.

    :param options: Parsed ``login`` arguments.
    :type options: argparse.Namespace
    :param path: Settings file.
    :type path: Path
    :return: Exit code.
    :rtype: int
    """
    print("\n".join(login(options, path)))
    return EXIT_OK


COMMANDS = {
    "run": run_command,
    "start": start_command,
    "stop": stop_command,
    "status": status_command,
    "supervise": supervise_command,
}


def common_options() -> argparse.ArgumentParser:
    """
    The options every command takes. A command's own default would
    overwrite a ``--config`` given before it, so commands leave the
    value alone (``SUPPRESS``).

    :return: Parser holding them, for ``parents``.
    :rtype: argparse.ArgumentParser
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", type=Path, default=argparse.SUPPRESS, help=CONFIG_HELP
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line.

    :return: Parser for ``python -m agent``.
    :rtype: argparse.ArgumentParser
    """
    common = common_options()
    parser = argparse.ArgumentParser(
        prog=agent_command(os.environ), description=DESCRIPTION
    )
    parser.add_argument("--config", type=Path, default=None)
    commands = parser.add_subparsers(dest="command")
    add_login_parser(commands, common)
    for name, text in COMMAND_HELP.items():
        commands.add_parser(name, parents=[common], help=text)
    # Started by "start", never by a person: no help line.
    commands.add_parser("supervise", parents=[common])
    return parser


def add_login_parser(commands, common: argparse.ArgumentParser) -> None:
    """
    Describe ``login`` and its options (``LOGIN_OPTIONS``).

    :param commands: The subcommand registry.
    :type commands: argparse._SubParsersAction
    :param common: Options every command takes.
    :type common: argparse.ArgumentParser
    """
    login_parser = commands.add_parser(
        "login", parents=[common], help="Save this machine's settings."
    )
    for flag, options in LOGIN_OPTIONS.items():
        login_parser.add_argument(flag, **options)


@stops_cleanly("Stopped.")
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
            return login_command(options, path)
        config = AgentConfig.load(path)
        return COMMANDS[command](config, path)
    except (MissingSettingError, TokenRefusedError, ValueError) as error:
        return fail(error)


if __name__ == "__main__":
    raise SystemExit(main())
