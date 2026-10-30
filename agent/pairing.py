"""
Pairing this machine with a short code, so no token is copied: the
agent asks the API for a pairing, shows its code and a link, and waits
while you approve it in the web app; then it collects its own token.
"""

import getpass
import socket
import time
from collections.abc import Callable
from typing import Any

import httpx

from agent.config import RunnerKind

PAIRINGS_PATH = "/api/agent/pairings"
REQUEST_SECONDS = 10.0
SECONDS_PER_MINUTE = 60
# How the web app names each kind of machine.
TARGET_KINDS = {RunnerKind.SLURM: "slurm", RunnerKind.PROCESS: "local"}
EXPIRED_MESSAGE = (
    "The code expired before it was approved; run login again for a new one."
)
Show = Callable[[str], None]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


class PairingFailedError(Exception):
    """
    The pairing did not finish: the code expired, or the API could not
    be reached or refused.
    """


def ask_to_pair(http: httpx.Client, runner: str) -> dict[str, Any]:
    """
    Ask the API for a pairing, saying which machine this is (so you
    can tell it apart when you approve it).

    :param http: Client for the API.
    :type http: httpx.Client
    :param runner: How jobs run here (``slurm`` or ``process``).
    :type runner: str
    :return: The code to show, the secret, and timings.
    :rtype: dict[str, Any]
    :raises PairingFailedError: If the API refuses.
    """
    machine = {
        "hostname": socket.gethostname(),
        "username": getpass.getuser(),
        "kind": TARGET_KINDS[RunnerKind(runner)],
    }
    response = http.post(PAIRINGS_PATH, json=machine)
    if response.status_code != httpx.codes.CREATED:
        refusal = f"The API refused to pair (HTTP {response.status_code})"
        raise PairingFailedError(refusal)
    return response.json()


def instructions(started: dict[str, Any]) -> list[str]:
    """
    What to tell the person: where to approve the code, and for how
    long it works.

    :param started: The API's answer to ``ask_to_pair``.
    :type started: dict[str, Any]
    :return: Lines to print.
    :rtype: list[str]
    """
    code = started["code"]
    minutes = started["expires_in"] // SECONDS_PER_MINUTE
    link = started.get("approve_url")
    where = f"open {link}" if link else "open AtomField's Pair page"
    return [
        f"To connect this machine, {where} while signed in,",
        f"and approve the code {code} within {minutes} minutes.",
        "Waiting for your approval...",
    ]


def token_from(response: httpx.Response) -> str:
    """
    The token in the API's answer, once the code is approved.

    :param response: The answer to asking for the token.
    :type response: httpx.Response
    :return: The agent token.
    :rtype: str
    :raises PairingFailedError: If the code expired or was refused.
    """
    if response.status_code == httpx.codes.OK:
        return response.json()["token"]
    if response.status_code == httpx.codes.NOT_FOUND:
        raise PairingFailedError(EXPIRED_MESSAGE)
    raise PairingFailedError(f"The API answered HTTP {response.status_code}")


def wait_for_token(
    http: httpx.Client,
    started: dict[str, Any],
    sleep: Sleep,
    clock: Clock = time.monotonic,
) -> str:
    """
    Ask every few seconds whether the code was approved.

    :param http: Client for the API.
    :type http: httpx.Client
    :param started: The API's answer to ``ask_to_pair``.
    :type started: dict[str, Any]
    :param sleep: Waits between questions.
    :type sleep: Sleep
    :param clock: Reads the time, for the code's expiry.
    :type clock: Clock
    :return: The agent token.
    :rtype: str
    :raises PairingFailedError: If the code expires first, or the API
        refuses.
    """
    path = f"{PAIRINGS_PATH}/{started['code']}/token"
    deadline = clock() + started["expires_in"]
    while clock() < deadline:
        sleep(started["interval"])
        response = http.post(path, json={"secret": started["secret"]})
        if response.status_code != httpx.codes.ACCEPTED:
            return token_from(response)
    raise PairingFailedError(EXPIRED_MESSAGE)


def pair(
    api_url: str,
    runner: str,
    show: Show = print,
    sleep: Sleep = time.sleep,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """
    Pair this machine, and return its new agent token.

    :param api_url: The API's address.
    :type api_url: str
    :param runner: How jobs run here (``slurm`` or ``process``).
    :type runner: str
    :param show: Prints a line for the person.
    :type show: Show
    :param sleep: Waits between questions.
    :type sleep: Sleep
    :param transport: How requests travel (tests pass a fake).
    :type transport: httpx.BaseTransport | None
    :return: The agent token.
    :rtype: str
    :raises PairingFailedError: If pairing did not finish.
    """
    base = api_url.rstrip("/")
    try:
        with httpx.Client(
            base_url=base, timeout=REQUEST_SECONDS, transport=transport
        ) as http:
            started = ask_to_pair(http, runner)
            for line in instructions(started):
                show(line)
            return wait_for_token(http, started, sleep)
    except httpx.HTTPError as error:
        raise PairingFailedError(f"Could not reach {base} ({error})") from error
