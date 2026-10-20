"""read_file: show the model a slice of a text file with line numbers."""

from __future__ import annotations

from typing import Any

from repo_ask.tools.base import Tool, ToolError, ToolSpec
from repo_ask.workspace import Workspace, WorkspaceError

DEFAULT_MAX_LINES = 300
BINARY_SNIFF_BYTES = 8_000


class ReadFileTool(Tool):
    spec = ToolSpec(
        name="read_file",
        description=(
            "Read a text file from the project and return its contents with line numbers. "
            "Paths are relative to the project root (for example 'src/app/main.py'). "
            f"At most {DEFAULT_MAX_LINES} lines are returned per call; for longer files, "
            "call again with a different start_line. Use the returned line numbers when "
            "citing code. Cannot read binary files, secrets (.env, keys) or files outside "
            "the project."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-based). Defaults to 1.",
                    "minimum": 1,
                },
                "max_lines": {
                    "type": "integer",
                    "description": (
                        f"How many lines to return. Defaults to {DEFAULT_MAX_LINES}, "
                        f"which is also the maximum."
                    ),
                    "minimum": 1,
                    "maximum": DEFAULT_MAX_LINES,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )

    def run(self, workspace: Workspace, **kwargs: Any) -> str:
        path_arg = kwargs.get("path")
        if not isinstance(path_arg, str):
            raise ToolError("'path' is required and must be a string.")
        start_line = _positive_int(kwargs.get("start_line", 1), "start_line")
        max_lines = min(
            _positive_int(kwargs.get("max_lines", DEFAULT_MAX_LINES), "max_lines"),
            DEFAULT_MAX_LINES,
        )

        try:
            path = workspace.resolve(path_arg)
        except WorkspaceError as exc:
            raise ToolError(str(exc)) from exc

        if path.is_dir():
            raise ToolError(f"{path_arg!r} is a directory, not a file. Use list_dir instead.")
        if not path.is_file():
            raise ToolError(f"File not found: {path_arg!r}")

        raw = path.read_bytes()
        if b"\0" in raw[:BINARY_SNIFF_BYTES]:
            raise ToolError(f"{path_arg!r} looks like a binary file and cannot be read as text.")
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        total = len(lines)

        if total == 0:
            return f"{workspace.display(path)} is empty (0 lines)."
        if start_line > total:
            raise ToolError(f"start_line {start_line} is past the end of the file ({total} lines).")

        end_line = min(start_line + max_lines - 1, total)
        width = len(str(end_line))
        body = "\n".join(
            f"{number:>{width}}| {lines[number - 1]}" for number in range(start_line, end_line + 1)
        )
        header = f"{workspace.display(path)} (lines {start_line}-{end_line} of {total})"
        footer = ""
        if end_line < total:
            footer = f"\n[{total - end_line} more lines. Call again with start_line={end_line + 1}]"
        return f"{header}\n{body}{footer}"


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"'{name}' must be an integer.")
    if value < 1:
        raise ToolError(f"'{name}' must be at least 1.")
    return value
