from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_ask.workspace import Workspace, WorkspaceError


def test_resolves_relative_path_inside_root(workspace: Workspace, repo: Path) -> None:
    assert workspace.resolve("src/app.py") == repo / "src" / "app.py"
    assert workspace.display(repo / "src" / "app.py") == "src/app.py"


def test_root_itself_is_allowed(workspace: Workspace, repo: Path) -> None:
    assert workspace.resolve(".") == repo


@pytest.mark.parametrize("bad", ["../etc/passwd", "src/../../x", "/etc/passwd", "", "  "])
def test_rejects_escapes_and_absolute_paths(workspace: Workspace, bad: str) -> None:
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


def test_rejects_symlink_pointing_outside(
    workspace: Workspace, repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("nope")
    os.symlink(outside, repo / "link.txt")
    with pytest.raises(WorkspaceError, match="escapes"):
        workspace.resolve("link.txt")


@pytest.mark.parametrize(
    "path", [".env", ".env.local", "node_modules/pkg.js", ".git/config", "certs/server.pem"]
)
def test_rejects_ignored_and_secret_paths(workspace: Workspace, path: str) -> None:
    with pytest.raises(WorkspaceError, match="excluded"):
        workspace.resolve(path)


def test_root_must_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        Workspace(tmp_path / "missing")
