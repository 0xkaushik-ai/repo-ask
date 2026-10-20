"""A scripted stand-in for the real model.

You give it a list of responses; it returns them in order and records every
request it received. This is what makes the agent loop testable without a
network or an API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repo_ask.model import ModelResponse, ToolCall, Usage


def tool_turn(*calls: tuple[str, dict[str, Any]]) -> ModelResponse:
    """A model response that asks for one or more tool calls."""
    tool_calls = [
        ToolCall(id=f"call_{i}", name=name, input=args) for i, (name, args) in enumerate(calls)
    ]
    raw = [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in tool_calls]
    return ModelResponse(
        text="", tool_calls=tool_calls, stop_reason="tool_use", raw_content=raw, usage=Usage(10, 5)
    )


def answer_turn(text: str) -> ModelResponse:
    """A model response that gives a final answer."""
    return ModelResponse(
        text=text,
        tool_calls=[],
        stop_reason="end_turn",
        raw_content=[{"type": "text", "text": text}],
        usage=Usage(10, 5),
    )


@dataclass
class FakeModel:
    responses: list[ModelResponse]
    requests: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse:
        # Deep-copy the messages so later mutation by the agent doesn't rewrite history.
        self.requests.append(
            {"system": system, "messages": [dict(m) for m in messages], "tools": tools}
        )
        if not self.responses:
            raise AssertionError("FakeModel ran out of scripted responses")
        return self.responses.pop(0)
