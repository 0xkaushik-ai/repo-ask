# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Planned
- `list_dir` and `grep` tools with result caps.
- Benchmark questions with known answers.

## [0.1.0] - 2026-10-20

### Added
- Agent loop with step cap, repeated-call detection, oversized-output truncation, and
  error-as-text handling for unknown tools, tool errors and tool crashes.
- `read_file` tool: line-numbered output, 300-line pagination, binary detection,
  actionable error messages.
- Workspace sandbox: rejects path escapes, symlinks out of the root, ignored
  directories and secret-looking files.
- Anthropic model adapter behind a `ModelClient` protocol, with early credential check
  and mapped SDK errors.
- `repo-ask` CLI with live tool-call display, `--quiet`, `--verbose`, `--effort`,
  `--max-steps`, `--model`, `-C`, and `REPO_ASK_*` environment overrides.
- Offline test suite (47 tests) using a scripted fake model.
