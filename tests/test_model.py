"""Tests for the Anthropic adapter, using a stub client so no network is touched."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import Message, StopReason, TextBlock, ToolUseBlock
from anthropic.types import Usage as ApiUsage

from repo_ask.config import Settings
from repo_ask.model import AnthropicModel, ModelError, Usage


def make_message(content: list[Any], stop_reason: StopReason = "end_turn") -> Message:
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=content,
        stop_reason=stop_reason,
        usage=ApiUsage(input_tokens=100, output_tokens=20, cache_read_input_tokens=40),
    )


class StubStream:
    def __init__(self, message: Message) -> None:
        self._message = message

    def get_final_message(self) -> Message:
        return self._message


class StubClient:
    """Mimics `anthropic.Anthropic().messages.stream(...)`. Records kwargs; returns or raises."""

    api_key = "sk-test"
    auth_token = None
    credentials = None

    def __init__(self, result: Message | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    @contextmanager
    def stream(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        yield StubStream(self.result)


def model_with(result: Message | Exception) -> tuple[AnthropicModel, StubClient]:
    client = StubClient(result)
    return AnthropicModel(Settings(effort="low"), client=client), client  # type: ignore[arg-type]


def test_parses_text_and_tool_calls() -> None:
    message = make_message(
        [
            TextBlock(type="text", text="Let me look."),
            ToolUseBlock(type="tool_use", id="toolu_1", name="read_file", input={"path": "a.py"}),
        ],
        stop_reason="tool_use",
    )
    model, _ = model_with(message)

    response = model.complete(system="sys", messages=[{"role": "user", "content": "q"}], tools=[])

    assert response.text == "Let me look."
    assert response.stop_reason == "tool_use"
    assert [(c.id, c.name, c.input) for c in response.tool_calls] == [
        ("toolu_1", "read_file", {"path": "a.py"})
    ]
    assert response.raw_content == message.content
    assert response.usage == Usage(input_tokens=100, output_tokens=20, cache_read_tokens=40)


def test_sends_settings_to_the_api() -> None:
    model, client = model_with(make_message([TextBlock(type="text", text="hi")]))

    model.complete(system="sys", messages=[{"role": "user", "content": "q"}], tools=[{"name": "t"}])

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == "sys"
    assert call["output_config"] == {"effort": "low"}
    assert call["tools"] == [{"name": "t"}]
    assert "thinking" not in call  # Opus 5.5: thinking is always on; passing it is an error.


def api_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "match"),
    [
        (api_error(anthropic.AuthenticationError, 401), "ANTHROPIC_API_KEY"),
        (api_error(anthropic.NotFoundError, 404), "Model not found"),
        (api_error(anthropic.RateLimitError, 429), "Rate limited"),
        (api_error(anthropic.InternalServerError, 500), "API error 500"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com")
            ),
            "network",
        ),
    ],
)
def test_sdk_errors_become_model_errors(error: Exception, match: str) -> None:
    model, _ = model_with(error)
    with pytest.raises(ModelError, match=match):
        model.complete(system="s", messages=[], tools=[])


def test_missing_credentials_fail_early() -> None:
    client = StubClient(make_message([]))
    client.api_key = None  # type: ignore[assignment]
    with pytest.raises(ModelError, match="ANTHROPIC_API_KEY"):
        AnthropicModel(Settings(), client=client)  # type: ignore[arg-type]
