from __future__ import annotations

from pathlib import Path

import pytest

from repo_ask.tools.base import ToolError
from repo_ask.tools.read_file import DEFAULT_MAX_LINES, ReadFileTool
from repo_ask.workspace import Workspace

tool = ReadFileTool()


def test_reads_with_line_numbers(workspace: Workspace) -> None:
    out = tool.run(workspace, path="src/app.py")
    assert out.startswith("src/app.py (lines 1-5 of 5)")
    assert "1| import os" in out
    assert "5|     return 42" in out
    assert "more lines" not in out


def test_paginates_long_files(workspace: Workspace, repo: Path) -> None:
    (repo / "big.txt").write_text("\n".join(f"line {i}" for i in range(1, 1001)))
    first = tool.run(workspace, path="big.txt")
    assert f"(lines 1-{DEFAULT_MAX_LINES} of 1000)" in first
    assert f"start_line={DEFAULT_MAX_LINES + 1}" in first

    page = tool.run(workspace, path="big.txt", start_line=990, max_lines=50)
    assert "(lines 990-1000 of 1000)" in page
    assert "more lines" not in page


def test_max_lines_is_capped(workspace: Workspace, repo: Path) -> None:
    (repo / "big.txt").write_text("\n".join("x" for _ in range(1000)))
    out = tool.run(workspace, path="big.txt", max_lines=5000)
    assert f"(lines 1-{DEFAULT_MAX_LINES} of 1000)" in out


def test_empty_file(workspace: Workspace) -> None:
    assert "empty" in tool.run(workspace, path="empty.txt")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"path": "nope.py"}, "not found"),
        ({"path": "src"}, "directory"),
        ({"path": "image.png"}, "binary"),
        ({"path": ".env"}, "excluded"),
        ({"path": "../x"}, "escapes"),
        ({"path": "src/app.py", "start_line": 99}, "past the end"),
        ({"path": "src/app.py", "start_line": 0}, "at least 1"),
        ({"path": "src/app.py", "start_line": "2"}, "integer"),
        ({"path": 123}, "must be a string"),
        ({}, "required"),
    ],
)
def test_errors_are_tool_errors_with_helpful_text(
    workspace: Workspace, kwargs: dict, match: str
) -> None:
    with pytest.raises(ToolError, match=match):
        tool.run(workspace, **kwargs)


def test_spec_is_valid_for_the_api() -> None:
    api = tool.spec.to_api()
    assert api["name"] == "read_file"
    assert api["input_schema"]["required"] == ["path"]
    assert api["input_schema"]["additionalProperties"] is False
