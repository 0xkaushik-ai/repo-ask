from __future__ import annotations

from pathlib import Path

import pytest

from repo_ask.workspace import Workspace


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny fake project on disk."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import os\n\n\ndef main():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Demo\n")
    (tmp_path / ".env").write_text("SECRET=hunter2\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = 1;\n")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
    (tmp_path / "empty.txt").write_text("")
    return tmp_path


@pytest.fixture
def workspace(repo: Path) -> Workspace:
    return Workspace(repo)
