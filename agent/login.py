"""
``python -m agent login``: gather the settings an agent needs (from
flags, or by asking), pair this machine with a short code (or take a
token given as a flag), check the token with the API, and save them in
the settings file, readable only by you since it holds the token.

Settings already in the file are offered as the defaults, so running
``login`` again only changes what you change.
"""

import os
import shlex
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from agent.client import TokenRefusedError
from agent.config import (
    RunnerKind,
    agent_command,
    read_settings,
    write_settings,
)
from agent.pairing import pair

CHECK_SECONDS = 10.0
# Setting -> question, in the order they are asked.
QUESTIONS = {
    "api_url": "Address of the AtomField API",
    "runner": "How jobs run here: slurm or process",
    "work_folder": "Work folder (job folders, log, state)",
    "python": "Python that runs the job scripts",
    "ssh_address": (
        "Address to copy results from: what you type after ssh on your "
        "own computer (an ssh shortcut, or you@cluster.address)"
    ),
}
Ask = Callable[[str], str]
Pair = Callable[[str, str], str]


def suggested_settings(existing: dict[str, Any]) -> dict[str, Any]:
    """
    Defaults: what the settings file already says, else good guesses
    for this machine.

    :param existing: Settings from the current file, if any.
    :type existing: dict[str, Any]
    :return: Settings to start from.
    :rtype: dict[str, Any]
    """
    guesses = {
        "runner": RunnerKind.SLURM
        if shutil.which("sbatch")
        else RunnerKind.PROCESS,
        "work_folder": str(Path.home() / "atomfield"),
        "python": sys.executable,
        # No guess for the copy address: this machine's own name (a
        # login node's) is rarely what works from your own computer.
        "max_jobs": 4,
    }
    return {**guesses, **existing}


def check_token(api_url: str, token: str) -> str | None:
    """
    Try the token: a heartbeat with no jobs is harmless, and shows the
    target as online in the web app.

    :param api_url: The API's address.
    :type api_url: str
    :param token: The agent token.
    :type token: str
    :return: A warning if the API could not be asked; None if it
        accepted the token.
    :rtype: str | None
    :raises TokenRefusedError: If the API refused the token.
    """
    try:
        response = httpx.post(
            f"{api_url.rstrip('/')}/api/agent/heartbeat",
            json={"jobs": []},
            headers={"Authorization": f"Bearer {token}"},
            timeout=CHECK_SECONDS,
        )
    except httpx.HTTPError as error:
        return f"could not reach {api_url} ({error})"
    if response.status_code == 401:
        raise TokenRefusedError("The API does not recognise this token")
    if response.status_code != 200:
        return f"the API answered HTTP {response.status_code}"
    return None


def from_flags(options) -> dict[str, Any]:
    """
    The settings given on the command line.

    :param options: Parsed ``login`` arguments.
    :type options: argparse.Namespace
    :return: Settings that were given (others left out).
    :rtype: dict[str, Any]
    """
    given = {
        "api_url": options.api_url,
        "token": options.token,
        "runner": options.runner,
        "work_folder": options.work_folder,
        "python": options.python,
        "pack_dir": options.pack_dir,
        "ssh_address": options.ssh_address,
        "max_jobs": options.max_jobs,
        "slurm_options": options.slurm_option,
        "slurm_setup": options.setup,
    }
    return {key: value for key, value in given.items() if value is not None}


def ask_missing(
    settings: dict[str, Any], given: dict[str, Any], ask: Ask
) -> None:
    """
    Ask for each setting not given as a flag; Enter keeps the default.
    The token is not asked for: pairing fetches it.

    :param settings: Settings so far; updated in place.
    :type settings: dict[str, Any]
    :param given: Settings given as flags (not asked again).
    :type given: dict[str, Any]
    :param ask: Asks a question and returns the answer.
    :type ask: Ask
    """
    for key, question in QUESTIONS.items():
        if key not in given:
            answer = ask(f"{question} [{settings.get(key, '')}]: ").strip()
            settings[key] = answer or settings.get(key, "")
    if settings["runner"] == RunnerKind.SLURM:
        ask_slurm(settings, given, ask)


def ask_slurm(
    settings: dict[str, Any], given: dict[str, Any], ask: Ask
) -> None:
    """
    Ask how this cluster wants jobs submitted.

    :param settings: Settings so far; updated in place.
    :type settings: dict[str, Any]
    :param given: Settings given as flags (not asked again).
    :type given: dict[str, Any]
    :param ask: Asks a question and returns the answer.
    :type ask: Ask
    """
    if "slurm_options" not in given:
        current = shlex.join(settings.get("slurm_options", []))
        answer = ask(f"Extra #SBATCH options, e.g. --account=x [{current}]: ")
        if answer.strip():
            settings["slurm_options"] = shlex.split(answer)
    if "slurm_setup" not in given:
        lines = []
        while line := ask("Setup line for each job (Enter to finish): "):
            lines.append(line.strip())
        if lines:
            settings["slurm_setup"] = lines


def gathered_settings(options, path: Path, ask: Ask) -> dict[str, Any]:
    """
    This machine's settings: flags first, then the settings file, then
    good guesses; whatever was not given as a flag is asked for, unless
    ``--yes``.

    :param options: Parsed ``login`` arguments.
    :type options: argparse.Namespace
    :param path: Settings file.
    :type path: Path
    :param ask: Asks a question and returns the answer.
    :type ask: Ask
    :return: The settings.
    :rtype: dict[str, Any]
    :raises ValueError: If the API address is missing.
    """
    given = from_flags(options)
    settings = {**suggested_settings(read_settings(path)), **given}
    if not options.yes:
        ask_missing(settings, given, ask)
    if not settings.get("api_url"):
        raise ValueError("The API address is needed")
    return settings


def needs_pairing(options, settings: dict[str, Any]) -> bool:
    """
    Whether to pair with a code: no token was given as a flag, and
    either none is saved or ``--pair`` asks for a fresh one.

    :param options: Parsed ``login`` arguments.
    :type options: argparse.Namespace
    :param settings: Settings so far.
    :type settings: dict[str, Any]
    :return: True to pair.
    :rtype: bool
    """
    if options.token:
        return False
    return options.pair or not settings.get("token")


def login(
    options,
    path: Path,
    ask: Ask = input,
    check: Callable[[str, str], str | None] = check_token,
    pairing: Pair = pair,
) -> list[str]:
    """
    Gather, pair (unless a token is given), check and save this
    machine's settings.

    :param options: Parsed ``login`` arguments.
    :type options: argparse.Namespace
    :param path: Settings file.
    :type path: Path
    :param ask: Asks a question (``input`` by default).
    :type ask: Ask
    :param check: Checks the token with the API.
    :type check: Callable[[str, str], str | None]
    :param pairing: Pairs with a code; returns the token.
    :type pairing: Pair
    :return: Lines to print.
    :rtype: list[str]
    :raises TokenRefusedError: If the API refused the token (nothing is
        saved).
    :raises PairingFailedError: If pairing did not finish.
    :raises ValueError: If the API address is missing.
    """
    settings = gathered_settings(options, path, ask)
    if needs_pairing(options, settings):
        settings["token"] = pairing(settings["api_url"], settings["runner"])
    warning = check(settings["api_url"], settings["token"])
    write_settings(path, settings)
    first = f"Warning: {warning}" if warning else "The API accepted the token."
    return [
        first,
        f"Saved {path}",
        f"Start the agent with: {agent_command(os.environ)} start",
    ]
