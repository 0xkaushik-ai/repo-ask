"""Tool registry: the set of tools the agent can use, looked up by name."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from repo_ask.tools.base import Tool, ToolError, ToolSpec, truncate
from repo_ask.tools.read_file import ReadFileTool

__all__ = [
    "ReadFileTool",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolSpec",
    "default_tools",
    "truncate",
]


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.spec.name in self._tools:
                raise ValueError(f"Duplicate tool name: {tool.spec.name}")
            self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def to_api(self) -> list[dict[str, Any]]:
        return [tool.spec.to_api() for tool in self._tools.values()]

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)


def default_tools() -> ToolRegistry:
    return ToolRegistry([ReadFileTool()])
