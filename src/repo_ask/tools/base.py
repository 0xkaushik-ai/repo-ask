"""The tool contract.

A tool is three things the model sees (name, description, JSON schema) plus one
thing it doesn't (the `run` implementation). The description IS the interface:
the model decides when and how to call a tool purely from that text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from repo_ask.workspace import Workspace


class ToolError(Exception):
    """An expected failure whose message should be sent back to the model.

    Raise this for things like "file not found" or "bad argument". The agent turns it
    into an error tool_result so the model can recover. Unexpected exceptions are
    handled separately and never crash the loop either.
    """


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_api(self) -> dict[str, Any]:
        """The shape the Anthropic Messages API expects in `tools=[...]`."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def run(self, workspace: Workspace, **kwargs: Any) -> str:
        """Execute the tool and return text for the model.

        Raise ToolError for user-facing failures.
        """


def truncate(text: str, max_chars: int) -> str:
    """Cap text so one tool result can't swallow the context window."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars] + f"\n\n[... truncated {omitted} characters ...]"
