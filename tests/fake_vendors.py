"""
Stand-ins for the AI vendors. ``FakeVendors`` is a small local web server
speaking their APIs, so tests drive the real libraries with no real key
and no money spent. ``FakeLlm`` stands in for a whole client, for tests
about what is done with a reply.
"""

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self

from app.ai.vendors import AiVendor, LlmError, LlmReply, Question

CLAUDE_PREFIX = "/claude"
OPENAI_PREFIX = "/openai/v1"
GEMINI_PREFIX = "/gemini/v1beta/openai"
LOOPBACK = "127.0.0.1"
KEY_IN_ERROR = "Incorrect API key provided: {key}"
ANSWER_TEXT = '{"summary": "done"}'


@dataclass
class Seen:
    """
    One request the fake server received.

    :param path: Its path and query.
    :type path: str
    :param headers: Its headers, names in lower case.
    :type headers: dict[str, str]
    :param body: Its JSON body, if it had one.
    :type body: dict[str, Any]
    """

    path: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass
class FakeVendors:
    """
    What the fake server answers, and what it was asked.

    :param status: Answer every request with this status, if not 200.
    :type status: int
    :param answered_by: The model named in replies.
    :type answered_by: str
    :param stop_reason: How a Claude message ends.
    :type stop_reason: str
    :param finish_reason: How an OpenAI-style reply ends.
    :type finish_reason: str
    :param refusal: The refusal in an OpenAI-style reply.
    :type refusal: str | None
    :param key_in_errors: The key quoted in error replies, as vendors do.
    :type key_in_errors: str
    :param claude_models: What Claude's model list says.
    :type claude_models: list[dict[str, Any]]
    :param compatible_models: What the other model list says.
    :type compatible_models: list[str]
    :param seen: Every request, in order.
    :type seen: list[Seen]
    :param url: Where it listens, once started.
    :type url: str
    """

    status: int = 200
    answered_by: str = "model-that-answered"
    stop_reason: str = "end_turn"
    finish_reason: str = "stop"
    refusal: str | None = None
    key_in_errors: str = ""
    claude_models: list[dict[str, Any]] = field(default_factory=list)
    compatible_models: list[str] = field(default_factory=list)
    seen: list[Seen] = field(default_factory=list)
    url: str = ""

    def claude_stream(self) -> bytes:
        """
        A streamed Claude message holding the answer.

        :return: Server-sent events.
        :rtype: bytes
        """
        start = {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": self.answered_by,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 11, "output_tokens": 1},
        }
        delta = {"stop_reason": self.stop_reason, "stop_sequence": None}
        text_delta = {"type": "text_delta", "text": ANSWER_TEXT}
        events = [
            {"type": "message_start", "message": start},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {"type": "content_block_delta", "index": 0, "delta": text_delta},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": delta,
                "usage": {"output_tokens": 22},
            },
            {"type": "message_stop"},
        ]
        frames = (
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            for event in events
        )
        return "".join(frames).encode("utf-8")

    def completion(self) -> dict[str, Any]:
        """
        An OpenAI-style reply holding the answer.

        :return: The chat completion.
        :rtype: dict[str, Any]
        """
        message = {
            "role": "assistant",
            "content": ANSWER_TEXT,
            "refusal": self.refusal,
        }
        return {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": self.answered_by,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": self.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 33,
                "completion_tokens": 44,
                "total_tokens": 77,
            },
        }

    def model_list(self, path: str) -> dict[str, Any]:
        """
        A vendor's list of models.

        :param path: The path asked for, which says which vendor.
        :type path: str
        :return: The list.
        :rtype: dict[str, Any]
        """
        if path.startswith(CLAUDE_PREFIX):
            return {
                "data": self.claude_models,
                "has_more": False,
                "first_id": None,
                "last_id": None,
            }
        data = [
            {"id": name, "object": "model", "created": 1, "owned_by": "fake"}
            for name in self.compatible_models
        ]
        return {"object": "list", "data": data}


def claude_model(name: str, can_answer: bool = True) -> dict[str, Any]:
    """
    One entry of Claude's list of models.

    :param name: The model.
    :type name: str
    :param can_answer: Whether it does fixed-shape replies and effort.
    :type can_answer: bool
    :return: The entry.
    :rtype: dict[str, Any]
    """
    return {
        "id": name,
        "type": "model",
        "display_name": name,
        "created_at": "2026-01-01T00:00:00Z",
        "capabilities": {
            "structured_outputs": {"supported": can_answer},
            "effort": {"supported": True},
        },
    }


def handler_for(fake: FakeVendors) -> type[BaseHTTPRequestHandler]:
    """
    The request handler of a fake server.

    :param fake: What it answers, and where it notes requests.
    :type fake: FakeVendors
    :return: The handler class.
    :rtype: type[BaseHTTPRequestHandler]
    """

    class Handler(BaseHTTPRequestHandler):
        """
        Answers as ``fake`` says.
        """

        def log_message(self, *args: Any) -> None:
            """
            Say nothing while tests run.

            :param args: What would be printed.
            :type args: Any
            """

        def answer(self, status: int, body: bytes, kind: str) -> None:
            """
            Send one answer.

            :param status: HTTP status.
            :type status: int
            :param body: The body.
            :type body: bytes
            :param kind: Its content type.
            :type kind: str
            """
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def answer_json(self, status: int, payload: dict[str, Any]) -> None:
            """
            Send one JSON answer.

            :param status: HTTP status.
            :type status: int
            :param payload: The body.
            :type payload: dict[str, Any]
            """
            body = json.dumps(payload).encode("utf-8")
            self.answer(status, body, "application/json")

        def note_request(self) -> None:
            """
            Remember this request.
            """
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            fake.seen.append(
                Seen(
                    path=self.path,
                    headers={
                        name.lower(): value
                        for name, value in self.headers.items()
                    },
                    body=json.loads(raw) if raw else {},
                )
            )

        def refuse(self) -> None:
            """
            Answer with the error ``fake`` is set to, quoting the key as
            vendors do.
            """
            message = KEY_IN_ERROR.format(key=fake.key_in_errors)
            payload = {
                "type": "error",
                "error": {"type": "error", "message": message},
            }
            self.answer_json(fake.status, payload)

        def do_GET(self) -> None:
            """
            A list of models, or the set error.
            """
            self.note_request()
            if fake.status != 200:
                self.refuse()
                return
            self.answer_json(200, fake.model_list(self.path))

        def do_POST(self) -> None:
            """
            A model's reply, or the set error.
            """
            self.note_request()
            if fake.status != 200:
                self.refuse()
            elif self.path.startswith(CLAUDE_PREFIX):
                events = fake.claude_stream()
                self.answer(200, events, "text/event-stream")
            else:
                self.answer_json(200, fake.completion())

    return Handler


def serving(fake: FakeVendors) -> Iterator[FakeVendors]:
    """
    Run a fake server until the generator is closed; a fixture's body.

    :param fake: What it answers.
    :type fake: FakeVendors
    :return: The same object, with ``url`` set.
    :rtype: Iterator[FakeVendors]
    """
    server = ThreadingHTTPServer((LOOPBACK, 0), handler_for(fake))
    fake.url = f"http://{LOOPBACK}:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@dataclass
class FakeLlm:
    """
    A whole client, for tests about what is done with a reply.

    :param models: What ``list_models`` returns.
    :type models: list[str]
    :param reply: What ``ask`` returns.
    :type reply: LlmReply | None
    :param error: What every call raises, if set.
    :type error: LlmError | None
    :param questions: Every question asked.
    :type questions: list[Question]
    :param used: Who made each client: (vendor, key).
    :type used: list[tuple[AiVendor, str]]
    """

    models: list[str] = field(default_factory=list)
    reply: LlmReply | None = None
    error: LlmError | None = None
    questions: list[Question] = field(default_factory=list)
    used: list[tuple[AiVendor, str]] = field(default_factory=list)

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
        Nothing to close.

        :param kind: What was raised, if anything.
        :type kind: type[BaseException] | None
        :param error: The exception, if any.
        :type error: BaseException | None
        :param trace: Its traceback, if any.
        :type trace: TracebackType | None
        """

    async def list_models(self) -> list[str]:
        """
        The models set.

        :return: Their names.
        :rtype: list[str]
        :raises LlmError: If one is set.
        """
        if self.error is not None:
            raise self.error
        return self.models

    async def ask(self, question: Question) -> LlmReply:
        """
        Note the question, and give the reply set.

        :param question: The question.
        :type question: Question
        :return: The reply.
        :rtype: LlmReply
        :raises LlmError: If one is set.
        """
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        assert self.reply is not None
        return self.reply

    def factory(self) -> Callable[[AiVendor, str], "FakeLlm"]:
        """
        A stand-in for ``client_for`` that always gives this object.

        :return: The factory.
        :rtype: Callable[[AiVendor, str], FakeLlm]
        """

        def make_client(vendor: AiVendor, key: str) -> "FakeLlm":
            """
            Note who asked, and give this client.

            :param vendor: The vendor.
            :type vendor: AiVendor
            :param key: The key.
            :type key: str
            :return: This client.
            :rtype: FakeLlm
            """
            self.used.append((vendor, key))
            return self

        return make_client
