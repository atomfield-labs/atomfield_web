"""
Calling a vendor's model with a person's key. The vendors don't share
one API, so this is the one place that knows them: OpenAI and Gemini
share a class through OpenAI's library, and Claude has its own, because
Anthropic says its OpenAI-compatible layer isn't for production and it
always leaves the refusal field empty.

Errors become plain messages here, and the vendor's own text is dropped
(``from None``): it can quote part of the key.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType, ModuleType, TracebackType
from typing import Any, Protocol, Self

import anthropic
import openai
from anthropic.types import ModelInfo

# Room for a model's thinking as well as its answer.
MAX_OUTPUT_TOKENS = 16000
CALL_TIMEOUT_SECONDS = 240.0
CALL_RETRIES = 1
REPLY_NAME = "answer"
GEMINI_ADDRESS = "https://generativelanguage.googleapis.com/v1beta/openai/"
# Gemini may list a model as ``models/<name>`` and takes it as ``<name>``.
GEMINI_LIST_PREFIX = "models/"
SYSTEM_ROLE = "system"
USER_ROLE = "user"
CLAUDE_EFFORT = "high"
CLAUDE_STOP_DECLINED = "refusal"
CLAUDE_STOP_CUT_SHORT = "max_tokens"
CLAUDE_TEXT_BLOCK = "text"
# If a safety check wrongly declines chemistry or biology text, Anthropic
# retries on another Claude model. Only these models accept it.
CLAUDE_FALLBACK = {
    "betas": ["server-side-fallback-2026-07-01"],
    "fallbacks": "default",
}
CLAUDE_FALLBACK_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    }
)
CUT_SHORT_REASON = "length"
FILTERED_REASON = "content_filter"
# Models OpenAI and Gemini list that don't answer in text.
NOT_FOR_TEXT = (
    "aqa",
    "audio",
    "dall-e",
    "embedding",
    "image",
    "imagen",
    "live",
    "moderation",
    "realtime",
    "search",
    "sora",
    "transcribe",
    "tts",
    "veo",
    "whisper",
)

KEY_REFUSED = "The vendor refused this key. Check it on the Account page."
MODEL_UNKNOWN = (
    "The vendor does not offer this model to your key. Choose another on "
    "the Account page."
)
REQUEST_REFUSED = (
    "The vendor refused the request. This model may not support it, or your "
    "account may be out of credit. Choose another model or check your account."
)
OVER_LIMIT = (
    "The vendor says you are over a limit or out of credit. Try again later, "
    "or check your account with them."
)
VENDOR_TROUBLE = "The vendor had trouble answering. Try again."
UNREACHABLE = "Could not reach the vendor. Try again."
DECLINED = "The model declined to read this. Try another model."
CUT_SHORT = "The answer was cut short. Ask again, or try another model."
FREE_GEMINI_WARNING = (
    "Free Gemini keys: Google may train on what you send, and people may "
    "read it. Use a paid key for unpublished work."
)

ASKING_MESSAGES = MappingProxyType(
    {
        400: REQUEST_REFUSED,
        401: KEY_REFUSED,
        402: OVER_LIMIT,
        403: KEY_REFUSED,
        404: MODEL_UNKNOWN,
        429: OVER_LIMIT,
    }
)
# Listing models is how a key is checked, and Gemini answers a bad key
# with a 400.
CHECKING_MESSAGES = MappingProxyType(
    {**ASKING_MESSAGES, 400: KEY_REFUSED, 404: KEY_REFUSED}
)


class AiVendor(StrEnum):
    """
    Whose model a key is for.
    """

    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


class LlmError(Exception):
    """
    A call failed. Its message is written for the person, and is safe to
    store and show.
    """


@dataclass(frozen=True, slots=True)
class Question:
    """
    One request to a model.

    :param model: The model's name.
    :type model: str
    :param system: The instructions.
    :type system: str
    :param user: What the model is to read.
    :type user: str
    :param schema: The JSON schema its reply must fit.
    :type schema: dict[str, Any]
    """

    model: str
    system: str
    user: str
    schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LlmReply:
    """
    A model's reply.

    :param text: The reply, JSON fitting the question's schema.
    :type text: str
    :param model: The model that answered, which a fallback can change.
    :type model: str
    :param input_tokens: Tokens read.
    :type input_tokens: int
    :param output_tokens: Tokens written.
    :type output_tokens: int
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LlmClient(Protocol):
    """
    All the rest of the server knows about a vendor.
    """

    async def __aenter__(self) -> Self:
        """
        Start using the client.

        :return: The client.
        :rtype: Self
        """

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """
        Close its connections.

        :param kind: What was raised, if anything.
        :type kind: type[BaseException] | None
        :param error: The exception, if any.
        :type error: BaseException | None
        :param trace: Its traceback, if any.
        :type trace: TracebackType | None
        """

    async def list_models(self) -> list[str]:
        """
        The models this key can ask, which also proves the key works.

        :return: Model names, sorted.
        :rtype: list[str]
        :raises LlmError: If the vendor refuses or can't be reached.
        """

    async def ask(self, question: Question) -> LlmReply:
        """
        Ask a model one question.

        :param question: The question.
        :type question: Question
        :return: Its reply.
        :rtype: LlmReply
        :raises LlmError: If it can't be asked, or doesn't fully answer.
        """


@contextmanager
def plain_errors(
    library: ModuleType, messages: Mapping[int, str]
) -> Iterator[None]:
    """
    Turn a vendor library's errors into messages for the person.

    :param library: ``anthropic`` or ``openai``, whose errors to catch.
    :type library: ModuleType
    :param messages: HTTP status -> message.
    :type messages: Mapping[int, str]
    :return: Nothing; wraps the call.
    :rtype: Iterator[None]
    :raises LlmError: In place of the library's error.
    """
    try:
        yield
    except library.APIStatusError as error:
        message = messages.get(error.status_code, VENDOR_TROUBLE)
        raise LlmError(message) from None
    except library.APIConnectionError:
        raise LlmError(UNREACHABLE) from None


class SdkClient:
    """
    What both clients share: holding a vendor library's client, and
    closing its connections.
    """

    def __init__(self, sdk: Any) -> None:
        """
        :param sdk: The library's client, which holds the key.
        :type sdk: Any
        """
        self.sdk = sdk

    async def __aenter__(self) -> Self:
        """
        Start using the client.

        :return: The client.
        :rtype: Self
        """
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """
        Close its connections.

        :param kind: What was raised, if anything.
        :type kind: type[BaseException] | None
        :param error: The exception, if any.
        :type error: BaseException | None
        :param trace: Its traceback, if any.
        :type trace: TracebackType | None
        """
        await self.sdk.close()


def claude_can_answer(model: ModelInfo) -> bool:
    """
    Whether a Claude model takes what ``ClaudeClient.ask`` sends.

    :param model: A listed model.
    :type model: ModelInfo
    :return: True if it does fixed-shape replies and effort levels, or if
        the vendor doesn't say.
    :rtype: bool
    """
    known = model.capabilities
    if known is None:
        return True
    return known.structured_outputs.supported and known.effort.supported


def claude_reply(message: Any) -> LlmReply:
    """
    Read a finished Claude message, checking how it stopped first: a
    declined message may hold nothing, or only part of an answer.

    :param message: The final message.
    :type message: Any
    :return: The reply.
    :rtype: LlmReply
    :raises LlmError: If the model declined or was cut short.
    """
    if message.stop_reason == CLAUDE_STOP_DECLINED:
        raise LlmError(DECLINED)
    if message.stop_reason == CLAUDE_STOP_CUT_SHORT:
        raise LlmError(CUT_SHORT)
    texts = (
        block.text
        for block in message.content
        if block.type == CLAUDE_TEXT_BLOCK
    )
    return LlmReply(
        text="".join(texts),
        model=message.model,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )


class ClaudeClient(SdkClient):
    """
    Claude, through Anthropic's library.
    """

    async def list_models(self) -> list[str]:
        """
        The Claude models this key can ask and that can answer us.

        :return: Model names, sorted.
        :rtype: list[str]
        :raises LlmError: If the vendor refuses or can't be reached.
        """
        with plain_errors(anthropic, CHECKING_MESSAGES):
            listed = [model async for model in self.sdk.models.list()]
        return sorted(model.id for model in listed if claude_can_answer(model))

    async def ask(self, question: Question) -> LlmReply:
        """
        Ask a Claude model. Streamed, so a long reply can't hit a request
        timeout, though only the final message is used.

        :param question: The question.
        :type question: Question
        :return: Its reply.
        :rtype: LlmReply
        :raises LlmError: If it can't be asked, or doesn't fully answer.
        """
        fallback = (
            CLAUDE_FALLBACK if question.model in CLAUDE_FALLBACK_MODELS else {}
        )
        output = {
            "effort": CLAUDE_EFFORT,
            "format": {"type": "json_schema", "schema": question.schema},
        }
        with plain_errors(anthropic, ASKING_MESSAGES):
            async with self.sdk.beta.messages.stream(
                model=question.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=question.system,
                messages=[{"role": USER_ROLE, "content": question.user}],
                output_config=output,
                **fallback,
            ) as stream:
                message = await stream.get_final_message()
        return claude_reply(message)


def writes_text(model_name: str) -> bool:
    """
    Whether a listed OpenAI or Gemini model is one that answers in text.

    :param model_name: Its name.
    :type model_name: str
    :return: False for embedding, image, audio and similar models.
    :rtype: bool
    """
    return not any(word in model_name for word in NOT_FOR_TEXT)


def compatible_reply(response: Any) -> LlmReply:
    """
    Read an OpenAI-style reply, checking how it stopped first.

    :param response: The chat completion.
    :type response: Any
    :return: The reply.
    :rtype: LlmReply
    :raises LlmError: If the model declined or was cut short.
    """
    choice = response.choices[0]
    if choice.message.refusal or choice.finish_reason == FILTERED_REASON:
        raise LlmError(DECLINED)
    if choice.finish_reason == CUT_SHORT_REASON:
        raise LlmError(CUT_SHORT)
    return LlmReply(
        text=choice.message.content or "",
        model=response.model,
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )


class OpenAiCompatibleClient(SdkClient):
    """
    OpenAI, and Gemini at the address where Google speaks the same API.
    """

    def __init__(self, sdk: Any, length_limit: str) -> None:
        """
        :param sdk: OpenAI's client, set to this vendor's address.
        :type sdk: Any
        :param length_limit: What this vendor calls the output limit.
        :type length_limit: str
        """
        super().__init__(sdk)
        self.length_limit = length_limit

    async def list_models(self) -> list[str]:
        """
        The models this key can ask that answer in text.

        :return: Model names, sorted.
        :rtype: list[str]
        :raises LlmError: If the vendor refuses or can't be reached.
        """
        with plain_errors(openai, CHECKING_MESSAGES):
            listed = [model async for model in self.sdk.models.list()]
        names = (model.id.removeprefix(GEMINI_LIST_PREFIX) for model in listed)
        return sorted(name for name in names if writes_text(name))

    async def ask(self, question: Question) -> LlmReply:
        """
        Ask a model.

        :param question: The question.
        :type question: Question
        :return: Its reply.
        :rtype: LlmReply
        :raises LlmError: If it can't be asked, or doesn't fully answer.
        """
        shape = {"name": REPLY_NAME, "schema": question.schema, "strict": True}
        with plain_errors(openai, ASKING_MESSAGES):
            response = await self.sdk.chat.completions.create(
                model=question.model,
                messages=[
                    {"role": SYSTEM_ROLE, "content": question.system},
                    {"role": USER_ROLE, "content": question.user},
                ],
                response_format={"type": "json_schema", "json_schema": shape},
                **{self.length_limit: MAX_OUTPUT_TOKENS},
            )
        return compatible_reply(response)


def claude_client(key: str) -> LlmClient:
    """
    A client for Claude.

    :param key: The person's key.
    :type key: str
    :return: The client.
    :rtype: LlmClient
    """
    sdk = anthropic.AsyncAnthropic(
        api_key=key, timeout=CALL_TIMEOUT_SECONDS, max_retries=CALL_RETRIES
    )
    return ClaudeClient(sdk)


def openai_client(key: str) -> LlmClient:
    """
    A client for OpenAI.

    :param key: The person's key.
    :type key: str
    :return: The client.
    :rtype: LlmClient
    """
    sdk = openai.AsyncOpenAI(
        api_key=key, timeout=CALL_TIMEOUT_SECONDS, max_retries=CALL_RETRIES
    )
    return OpenAiCompatibleClient(sdk, "max_completion_tokens")


def gemini_client(key: str) -> LlmClient:
    """
    A client for Gemini, at Google's OpenAI-compatible address.

    :param key: The person's key.
    :type key: str
    :return: The client.
    :rtype: LlmClient
    """
    sdk = openai.AsyncOpenAI(
        api_key=key,
        base_url=GEMINI_ADDRESS,
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=CALL_RETRIES,
    )
    return OpenAiCompatibleClient(sdk, "max_tokens")


@dataclass(frozen=True, slots=True)
class VendorEntry:
    """
    What the platform knows about one vendor.

    :param title: Its name on screen.
    :type title: str
    :param default_model: Chosen for a new key, if the vendor lists it.
    :type default_model: str
    :param make_client: Makes a client from a key.
    :type make_client: Callable[[str], LlmClient]
    :param warning: What someone choosing it should know, if anything.
    :type warning: str | None
    """

    title: str
    default_model: str
    make_client: Callable[[str], LlmClient]
    warning: str | None = None


VENDORS = MappingProxyType(
    {
        AiVendor.CLAUDE: VendorEntry(
            "Claude", "claude-opus-5-5", claude_client
        ),
        AiVendor.OPENAI: VendorEntry("OpenAI", "gpt-6-astra", openai_client),
        AiVendor.GEMINI: VendorEntry(
            "Gemini", "gemini-3.8-flash", gemini_client, FREE_GEMINI_WARNING
        ),
    }
)


def client_for(vendor: AiVendor, key: str) -> LlmClient:
    """
    A client for a vendor, holding a person's key.

    :param vendor: The vendor.
    :type vendor: AiVendor
    :param key: The person's key.
    :type key: str
    :return: The client; use it in ``async with``.
    :rtype: LlmClient
    """
    return VENDORS[vendor].make_client(key)


def first_choice(vendor: AiVendor, models: list[str]) -> str:
    """
    The model a new key starts with.

    :param vendor: The vendor.
    :type vendor: AiVendor
    :param models: The models the key can ask.
    :type models: list[str]
    :return: The vendor's default if listed, else the first listed, else
        the default anyway (the vendor listed nothing to choose from).
    :rtype: str
    """
    default = VENDORS[vendor].default_model
    return default if default in models or not models else models[0]
