"""
Calling the vendors, through their real libraries, against a fake web
server: no real key, and no money spent. What a real vendor does today is
only proved by a real click, which needs a real key.
"""

import asyncio
import logging
from collections.abc import Iterator
from typing import Any

import anthropic
import openai
import pytest

from app.ai.vendors import (
    CHECKING_MESSAGES,
    CUT_SHORT,
    DECLINED,
    FREE_GEMINI_WARNING,
    GEMINI_ADDRESS,
    KEY_REFUSED,
    MAX_OUTPUT_TOKENS,
    MODEL_UNKNOWN,
    OVER_LIMIT,
    REQUEST_REFUSED,
    UNREACHABLE,
    VENDOR_TROUBLE,
    VENDORS,
    AiVendor,
    ClaudeClient,
    LlmClient,
    LlmError,
    OpenAiCompatibleClient,
    Question,
    first_choice,
    gemini_client,
    plain_errors,
)
from tests.fake_vendors import (
    ANSWER_TEXT,
    CLAUDE_PREFIX,
    GEMINI_PREFIX,
    OPENAI_PREFIX,
    FakeVendors,
    claude_model,
    serving,
)

KEY = "sk-test-key-that-must-never-show-1234"
SCHEMA = {"type": "object", "additionalProperties": False}
NOWHERE = "http://127.0.0.1:9"


def question(model: str = "some-model") -> Question:
    """
    A question to ask.

    :param model: The model.
    :type model: str
    :return: The question.
    :rtype: Question
    """
    return Question(model=model, system="Be brief.", user="Why?", schema=SCHEMA)


@pytest.fixture
def fake() -> Iterator[FakeVendors]:
    """
    A fake vendor server, running.

    :return: The server's settings and what it saw.
    :rtype: Iterator[FakeVendors]
    """
    yield from serving(FakeVendors(key_in_errors=KEY))


def claude(address: str) -> ClaudeClient:
    """
    A real Claude client, at a fake address, with no retries.

    :param address: Where it calls.
    :type address: str
    :return: The client.
    :rtype: ClaudeClient
    """
    sdk = anthropic.AsyncAnthropic(api_key=KEY, base_url=address, max_retries=0)
    return ClaudeClient(sdk)


def compatible(address: str, limit: str = "max_completion_tokens") -> Any:
    """
    A real OpenAI client, at a fake address, with no retries.

    :param address: Where it calls.
    :type address: str
    :param limit: What this vendor calls the output limit.
    :type limit: str
    :return: The client.
    :rtype: OpenAiCompatibleClient
    """
    sdk = openai.AsyncOpenAI(api_key=KEY, base_url=address, max_retries=0)
    return OpenAiCompatibleClient(sdk, limit)


def client_at(name: str, url: str) -> LlmClient:
    """
    Either kind of client, for tests of what they share.

    :param name: ``claude`` or ``compatible``.
    :type name: str
    :param url: The fake server.
    :type url: str
    :return: The client.
    :rtype: LlmClient
    """
    if name == "claude":
        return claude(f"{url}{CLAUDE_PREFIX}")
    return compatible(f"{url}{OPENAI_PREFIX}")


async def asked(client: LlmClient, model: str = "some-model") -> Any:
    """
    Ask a client one question and close it.

    :param client: The client.
    :type client: LlmClient
    :param model: The model.
    :type model: str
    :return: Its reply.
    :rtype: Any
    """
    async with client as llm:
        return await llm.ask(question(model))


async def listed(client: LlmClient) -> list[str]:
    """
    List a client's models and close it.

    :param client: The client.
    :type client: LlmClient
    :return: Model names.
    :rtype: list[str]
    """
    async with client as llm:
        return await llm.list_models()


def test_claude_is_asked_for_a_fixed_shape_and_gives_its_reply(
    fake: FakeVendors,
):
    """
    The question reaches Claude as its API wants, and the reply is read.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    reply = asyncio.run(asked(claude(f"{fake.url}{CLAUDE_PREFIX}")))
    assert reply.text == ANSWER_TEXT
    assert reply.model == fake.answered_by
    assert (reply.input_tokens, reply.output_tokens) == (11, 22)
    request = fake.seen[0]
    assert any(KEY in value for value in request.headers.values())
    assert request.body["model"] == "some-model"
    assert request.body["system"] == "Be brief."
    assert request.body["max_tokens"] == MAX_OUTPUT_TOKENS
    assert request.body["messages"] == [{"role": "user", "content": "Why?"}]
    output = request.body["output_config"]
    assert output["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert output["effort"] == "high"
    assert "temperature" not in request.body


def test_only_models_that_accept_it_ask_for_a_fallback(fake: FakeVendors):
    """
    A safety check's wrong refusal is retried on the models that allow
    it, and others are sent nothing they would refuse.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    address = f"{fake.url}{CLAUDE_PREFIX}"
    asyncio.run(asked(claude(address), "claude-opus-5-5"))
    asyncio.run(asked(claude(address), "claude-haiku-5-5"))
    accepts, refuses = fake.seen
    assert accepts.body["fallbacks"] == "default"
    assert "server-side-fallback" in accepts.headers["anthropic-beta"]
    assert "fallbacks" not in refuses.body
    assert "server-side-fallback" not in refuses.headers.get(
        "anthropic-beta", ""
    )


@pytest.mark.parametrize(
    ("stop_reason", "message"),
    [("refusal", DECLINED), ("max_tokens", CUT_SHORT)],
)
def test_claude_stopping_early_is_not_an_answer(
    fake: FakeVendors, stop_reason: str, message: str
):
    """
    A declined or cut-off message may hold part of an answer: it is
    reported, and the part is not used.

    :param fake: The fake server.
    :type fake: FakeVendors
    :param stop_reason: How the message ends.
    :type stop_reason: str
    :param message: What the person is told.
    :type message: str
    """
    fake.stop_reason = stop_reason
    with pytest.raises(LlmError, match=message):
        asyncio.run(asked(claude(f"{fake.url}{CLAUDE_PREFIX}")))


def test_claude_lists_only_models_that_can_answer(fake: FakeVendors):
    """
    A model that can't give a fixed-shape reply isn't offered.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    fake.claude_models = [
        claude_model("claude-b"),
        claude_model("claude-old", can_answer=False),
        claude_model("claude-a"),
    ]
    found = asyncio.run(listed(claude(f"{fake.url}{CLAUDE_PREFIX}")))
    assert found == ["claude-a", "claude-b"]


def test_openai_is_asked_for_a_strict_shape_and_gives_its_reply(
    fake: FakeVendors,
):
    """
    The question reaches OpenAI as its API wants, and the reply is read.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    reply = asyncio.run(asked(compatible(f"{fake.url}{OPENAI_PREFIX}")))
    assert reply.text == ANSWER_TEXT
    assert reply.model == fake.answered_by
    assert (reply.input_tokens, reply.output_tokens) == (33, 44)
    request = fake.seen[0]
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.body["max_completion_tokens"] == MAX_OUTPUT_TOKENS
    assert request.body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Why?"},
    ]
    shape = request.body["response_format"]["json_schema"]
    assert shape["schema"] == SCHEMA
    assert shape["strict"] is True


def test_gemini_uses_googles_address_and_warns_about_free_keys(
    fake: FakeVendors,
):
    """
    Gemini shares OpenAI's code at Google's address, with its own name
    for the output limit, and anyone choosing it sees the warning.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    assert str(gemini_client(KEY).sdk.base_url) == GEMINI_ADDRESS
    assert VENDORS[AiVendor.GEMINI].warning == FREE_GEMINI_WARNING
    assert VENDORS[AiVendor.CLAUDE].warning is None
    assert VENDORS[AiVendor.OPENAI].warning is None
    client = compatible(f"{fake.url}{GEMINI_PREFIX}", "max_tokens")
    asyncio.run(asked(client))
    assert fake.seen[0].body["max_tokens"] == MAX_OUTPUT_TOKENS


def test_compatible_lists_only_text_models_by_their_plain_names(
    fake: FakeVendors,
):
    """
    OpenAI and Gemini list every kind of model; only text ones are
    offered, without Gemini's prefix.

    :param fake: The fake server.
    :type fake: FakeVendors
    """
    fake.compatible_models = [
        "models/gemini-3.8-flash",
        "gpt-6-astra",
        "text-embedding-3-large",
        "whisper-1",
        "models/imagen-4",
        "gpt-6-audio",
    ]
    found = asyncio.run(listed(compatible(f"{fake.url}{OPENAI_PREFIX}")))
    assert found == ["gemini-3.8-flash", "gpt-6-astra"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"refusal": "No."}, DECLINED),
        ({"finish_reason": "content_filter"}, DECLINED),
        ({"finish_reason": "length"}, CUT_SHORT),
    ],
)
def test_a_compatible_vendor_stopping_early_is_not_an_answer(
    fake: FakeVendors, change: dict[str, str], message: str
):
    """
    A refused, filtered or cut-off reply is reported, and not used.

    :param fake: The fake server.
    :type fake: FakeVendors
    :param change: How this reply differs.
    :type change: dict[str, str]
    :param message: What the person is told.
    :type message: str
    """
    for name, value in change.items():
        setattr(fake, name, value)
    with pytest.raises(LlmError, match=message):
        asyncio.run(asked(compatible(f"{fake.url}{OPENAI_PREFIX}")))


@pytest.mark.parametrize("name", ["claude", "compatible"])
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (400, REQUEST_REFUSED),
        (401, KEY_REFUSED),
        (402, OVER_LIMIT),
        (403, KEY_REFUSED),
        (404, MODEL_UNKNOWN),
        (429, OVER_LIMIT),
        (500, VENDOR_TROUBLE),
    ],
)
def test_vendor_errors_become_plain_messages_without_the_key(
    fake: FakeVendors, name: str, status: int, message: str
):
    """
    The person is told what to do, and the vendor's own text, which can
    quote the key, goes nowhere: not in the message, not in the chain.

    :param fake: The fake server.
    :type fake: FakeVendors
    :param name: Which client.
    :type name: str
    :param status: What the vendor answers.
    :type status: int
    :param message: What the person is told.
    :type message: str
    """
    fake.status = status
    with pytest.raises(LlmError) as caught:
        asyncio.run(asked(client_at(name, fake.url)))
    assert str(caught.value) == message
    assert KEY not in str(caught.value)
    assert caught.value.__suppress_context__
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("name", ["claude", "compatible"])
@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_a_refusal_while_checking_a_key_blames_the_key(
    fake: FakeVendors, name: str, status: int
):
    """
    Listing models is how a key is checked, and Gemini answers a bad key
    with a 400, so all of these mean the same thing here.

    :param fake: The fake server.
    :type fake: FakeVendors
    :param name: Which client.
    :type name: str
    :param status: What the vendor answers.
    :type status: int
    """
    assert CHECKING_MESSAGES[status] == KEY_REFUSED
    fake.status = status
    with pytest.raises(LlmError, match=KEY_REFUSED):
        asyncio.run(listed(client_at(name, fake.url)))


@pytest.mark.parametrize(
    "client",
    [
        pytest.param(lambda: claude(NOWHERE), id="claude"),
        pytest.param(lambda: compatible(NOWHERE), id="compatible"),
    ],
)
def test_a_vendor_out_of_reach_says_so(client):
    """
    Nothing listens at the address.

    :param client: Makes the client.
    :type client: Callable
    """
    with pytest.raises(LlmError, match=UNREACHABLE):
        asyncio.run(asked(client()))


@pytest.mark.parametrize("name", ["claude", "compatible"])
def test_the_key_is_not_logged_even_at_debug(
    fake: FakeVendors, name: str, caplog: pytest.LogCaptureFixture
):
    """
    The libraries log a lot at debug level, and none of it is the key,
    on a good call or a refused one.

    :param fake: The fake server.
    :type fake: FakeVendors
    :param name: Which client.
    :type name: str
    :param caplog: Captures log records.
    :type caplog: pytest.LogCaptureFixture
    """
    with caplog.at_level(logging.DEBUG):
        asyncio.run(asked(client_at(name, fake.url)))
        fake.status = 401
        with pytest.raises(LlmError):
            asyncio.run(asked(client_at(name, fake.url)))
    assert caplog.records
    assert KEY not in caplog.text


def test_a_new_key_starts_with_the_vendors_default_model():
    """
    The default if listed, else the first listed, else the default.
    """
    default = VENDORS[AiVendor.CLAUDE].default_model
    assert first_choice(AiVendor.CLAUDE, ["a", default]) == default
    assert first_choice(AiVendor.CLAUDE, ["a", "b"]) == "a"
    assert first_choice(AiVendor.CLAUDE, []) == default


def test_other_exceptions_are_not_hidden():
    """
    Only a vendor's own errors become messages; a bug still shows.
    """
    with (
        pytest.raises(ZeroDivisionError),
        plain_errors(anthropic, CHECKING_MESSAGES),
    ):
        _ = 1 / 0
