"""The workspace: the directory the agent is allowed to read.

Every filesystem access by a tool goes through `Workspace.resolve`, which is the
single place that enforces "never read outside the project root". Keeping this
in one class means the tools stay simple and the safety rule is testable alone.
"""

from __future__ import annotations

from pathlib import Path

# Directories that are never useful for answering questions and often huge.
IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }
)

# Files that commonly hold secrets. Their contents are sent to a third-party API,
# so we refuse to read them even if the model asks.
SECRET_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".envrc",
        ".netrc",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }
)
SECRET_FILE_PREFIXES: tuple[str, ...] = (".env.",)
SECRET_FILE_SUFFIXES: tuple[str, ...] = (".pem", ".key", ".p12", ".pfx")


class WorkspaceError(Exception):
    """A path was rejected. The message is safe to show to the model."""


class Workspace:
    def __init__(self, root: Path | str) -> None:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise WorkspaceError(f"Workspace root is not a directory: {root}")
        self.root = root

    def resolve(self, relative: str) -> Path:
        """Turn a model-supplied path into an absolute path inside the workspace.

        Rejects absolute paths, `..` escapes and symlinks pointing outside the root.
        """
        if not relative or relative.strip() == "":
            raise WorkspaceError("Path must not be empty.")
        candidate = Path(relative)
        if candidate.is_absolute():
            raise WorkspaceError(
                f"Absolute paths are not allowed: {relative!r}. Use a path relative to the "
                "project root."
            )
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceError(f"Path escapes the project root: {relative!r}")
        if self.is_ignored(resolved):
            raise WorkspaceError(f"Path is excluded from reading: {relative!r}")
        return resolved

    def display(self, path: Path) -> str:
        """Path relative to the root, with forward slashes, for showing to the model/user."""
        return path.relative_to(self.root).as_posix()

    def is_ignored(self, path: Path) -> bool:
        """True if the path is inside an ignored directory or looks like a secret."""
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return True
        if any(part in IGNORED_DIR_NAMES for part in parts):
            return True
        return bool(parts) and self.is_secret_name(parts[-1])

    @staticmethod
    def is_secret_name(name: str) -> bool:
        return (
            name in SECRET_FILE_NAMES
            or name.startswith(SECRET_FILE_PREFIXES)
            or name.endswith(SECRET_FILE_SUFFIXES)
        )
