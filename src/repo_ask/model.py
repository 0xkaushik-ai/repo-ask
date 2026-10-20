"""The model boundary.

The agent loop talks to a `ModelClient` and never to the Anthropic SDK directly.
That gives us two things:
  1. Tests run against a scripted fake, with no network and no API key.
  2. Swapping providers later touches one file.

Messages are kept in the Anthropic Messages API shape (a list of dicts) because
it is the de-facto standard and it lets us replay the model's own content blocks
back unchanged, which the API requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import anthropic
from anthropic.types import MessageParam, OutputConfigParam, ToolParam

from repo_ask.config import Settings


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )


@dataclass(frozen=True)
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    # The provider's content blocks, replayed verbatim as the next assistant turn.
    raw_content: list[Any]
    usage: Usage = field(default_factory=Usage)
    # Set when stop_reason == "refusal": a short, human-readable explanation.
    refusal_explanation: str | None = None


class ModelClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


class ModelError(Exception):
    """A model call failed in a way the loop cannot recover from. Message is user-facing."""


class AnthropicModel:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self.settings = settings
        # Reads ANTHROPIC_API_KEY (or an `ant auth login` profile) automatically.
        self._client = client or anthropic.Anthropic()
        # The SDK only discovers missing credentials at request time, and raises a bare
        # TypeError. Checking here turns that into a clear message before any work is done.
        if not any((self._client.api_key, self._client.auth_token, self._client.credentials)):
            raise ModelError(
                "No API credentials found. Set ANTHROPIC_API_KEY or run `ant auth login`."
            )

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        try:
            with self._client.messages.stream(
                model=self.settings.model,
                max_tokens=self.settings.max_output_tokens,
                system=system,
                messages=cast(list[MessageParam], messages),
                tools=cast(list[ToolParam], tools),
                output_config=cast(OutputConfigParam, {"effort": self.settings.effort}),
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ModelError(
                "Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`."
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ModelError(f"Model not found: {self.settings.model!r}") from exc
        except anthropic.RateLimitError as exc:
            raise ModelError("Rate limited by the API. Wait a moment and try again.") from exc
        except anthropic.APIStatusError as exc:
            raise ModelError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelError("Could not reach the API. Check your network connection.") from exc

        return _parse(message)


def _parse(message: anthropic.types.Message) -> ModelResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            # Inputs are already parsed JSON; copy so tools can't mutate the replayed block.
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))

    refusal = None
    if message.stop_reason == "refusal":
        details = message.stop_details
        refusal = (details.explanation if details and details.explanation else None) or (
            "The model declined to answer."
        )

    usage = Usage(
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        cache_read_tokens=message.usage.cache_read_input_tokens or 0,
    )
    return ModelResponse(
        text="".join(text_parts),
        tool_calls=tool_calls,
        stop_reason=message.stop_reason or "end_turn",
        raw_content=list(message.content),
        usage=usage,
        refusal_explanation=refusal,
    )
