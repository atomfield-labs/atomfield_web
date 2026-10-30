"""
The agent's side of pairing: it asks for a code, shows where to
approve it, waits, and collects its token. The fake API answers with
the server's own schemas, so the two sides cannot drift apart.
"""

import json

import httpx
import pytest

from agent.pairing import (
    EXPIRED_MESSAGE,
    PAIRINGS_PATH,
    PairingFailedError,
    pair,
)
from app.schemas.pairings import PairingPoll, PairingRequest, PairingStarted

API_URL = "https://atomfield.example.ac.in"
CODE = "QKTW-MZRB"
STARTED = PairingStarted(
    code=CODE,
    secret="the-agents-own-secret",
    approve_url=f"{API_URL}/#pair/{CODE}",
    expires_in=600,
    interval=5,
)
TOKEN = {
    "token": "af_agent_paired",
    "target": {"id": "7d1f0b52-8c1f-4a52-9f0e-0c1b8f5c4a11"},
}


class FakeApi:
    """
    The pairing API, answering a pairing request and then the given
    statuses to each question about the token.

    :param token_answers: Status of each answer about the token.
    :type token_answers: list[int]
    """

    def __init__(self, token_answers: list[int]) -> None:
        """
        Set up the answers.

        :param token_answers: Status of each answer about the token.
        :type token_answers: list[int]
        """
        self.token_answers = iter(token_answers)
        self.bodies: list[dict] = []

    def answer(self, request: httpx.Request) -> httpx.Response:
        """
        Answer one call, checking its body against the server's schema.

        :param request: The agent's call.
        :type request: httpx.Request
        :return: The API's answer.
        :rtype: httpx.Response
        """
        body = json.loads(request.content)
        self.bodies.append(body)
        if request.url.path == PAIRINGS_PATH:
            PairingRequest.model_validate(body)
            return httpx.Response(201, json=STARTED.model_dump())
        PairingPoll.model_validate(body)
        status = next(self.token_answers)
        return httpx.Response(status, json=TOKEN if status == 200 else {})


def test_the_agent_shows_where_to_approve_and_collects_its_token():
    """
    The link and code are shown; the agent asks every interval until
    approved, with its own secret, and returns the token.
    """
    api = FakeApi([202, 202, 200])
    shown, waits = [], []
    token = pair(
        API_URL,
        "slurm",
        show=shown.append,
        sleep=waits.append,
        transport=httpx.MockTransport(api.answer),
    )
    assert token == TOKEN["token"]
    assert any(STARTED.approve_url in line for line in shown)
    assert any(CODE in line for line in shown)
    assert waits == [STARTED.interval] * 3
    assert api.bodies[0]["kind"] == "slurm"
    assert api.bodies[-1] == {"secret": STARTED.secret}


def test_an_expired_code_ends_pairing_with_a_clear_message():
    """
    If the code ran out (or was never approved), the agent says so
    instead of waiting forever.
    """
    transport = httpx.MockTransport(FakeApi([202, 404]).answer)
    with pytest.raises(PairingFailedError, match=EXPIRED_MESSAGE):
        pair(
            API_URL,
            "process",
            show=print,
            sleep=lambda _: None,
            transport=transport,
        )


def test_an_unreachable_server_is_named():
    """
    No answer at all: the error names the address it tried.
    """

    def unreachable(request: httpx.Request) -> httpx.Response:
        """
        Fail like a server that is down.

        :param request: The agent's call.
        :type request: httpx.Request
        :return: Never returns.
        :rtype: httpx.Response
        """
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(unreachable)
    with pytest.raises(PairingFailedError, match=f"Could not reach {API_URL}"):
        pair(API_URL, "slurm", show=print, transport=transport)
