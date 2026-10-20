# Contributing

Thanks for your interest. `repo-ask` is intentionally small; the best contributions keep
it that way.

## Before you start

- Read [docs/architecture.md](docs/architecture.md) so your change fits the design.
- Open an issue for anything bigger than a bug fix, so we can agree on the shape first.
- New tools must be **read-only**. Writing files or running commands is out of scope.

## Workflow

1. Fork and clone, then `uv sync`.
2. Create a branch: `git checkout -b feat/short-name`.
3. Make the change with tests. Every tool needs tests for its error messages too.
4. Run the checks: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`.
5. Open a pull request. Describe what changed and why; paste a `--verbose` trace if the
   change affects agent behaviour.

See [docs/development.md](docs/development.md) for the layout and how to add a tool.

## Commit messages

Use the conventional prefix: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
One logical change per commit.

## Code style

- `ruff` and `mypy --strict` are the style guide. If they pass, the style is right.
- Comments explain *why*, not *what*. Match the density of the surrounding code.
- No new dependencies without a reason in the pull request.
