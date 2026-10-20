# repo-ask

Ask questions about any codebase from the command line.

```
$ cd some-unfamiliar-project
$ repo-ask "where is authentication handled and how does it work?"

 1 read_file(path='src/middleware/auth.py')
 2 read_file(path='src/config.py')

Authentication is handled by `AuthMiddleware` in `src/middleware/auth.py:23`. It reads
the `Authorization` header, verifies the JWT with the secret from `src/config.py:41` ...

2 steps · 4,812 in / 310 out tokens
```

`repo-ask` is a small, **read-only** AI agent. It reads the project's files, decides what
to read next, and answers with `file:line` citations so you can verify every claim.
It never edits files and never runs commands.

It is also a deliberately small, fully tested example of an **agent harness**: the loop,
tools, model boundary, safety and context controls that turn a language model into a
working agent. See [docs/architecture.md](docs/architecture.md) if that is what you are here for.

> **Status:** alpha. Milestone 1 (agent loop + `read_file`) is complete. `list_dir` and
> `grep` are next; see the [roadmap](#roadmap).

## Install

Requires Python 3.11+ and an [Anthropic API key](https://console.anthropic.com/).

```bash
# with uv (recommended)
uv tool install git+https://github.com/0xkaushik-ai/repo-ask

# or with pipx
pipx install git+https://github.com/0xkaushik-ai/repo-ask

export ANTHROPIC_API_KEY=sk-ant-...
```

Verify:

```bash
repo-ask --version
```

## Usage

```bash
repo-ask "what does this project do?"
repo-ask "what does main() return?" -C path/to/project
repo-ask "which function parses the config?" --effort low     # cheaper
repo-ask "explain the agent loop" --quiet > answer.md         # answer only, to a file
repo-ask "..." --verbose                                      # show full tool output
```

Progress (tool calls) goes to **stderr**, the answer goes to **stdout**, so piping and
redirecting work as expected.

### Options

| Flag | Default | Meaning |
|---|---|---|
| `-C, --root DIR` | `.` | Project directory to read |
| `--model ID` | `claude-opus-5-5` | Model to use |
| `--max-steps N` | `25` | Hard cap on model calls per question |
| `--effort low\|medium\|high` | `medium` | Reasoning depth; lower is cheaper and faster |
| `-q, --quiet` | | Print only the final answer |
| `-v, --verbose` | | Show full tool output and debug logs |

Every default can also be set with an environment variable: `REPO_ASK_MODEL`,
`REPO_ASK_MAX_STEPS`, `REPO_ASK_EFFORT`, `REPO_ASK_MAX_OUTPUT_TOKENS`,
`REPO_ASK_MAX_TOOL_RESULT_CHARS`. CLI flags win over environment variables.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Answered |
| `1` | Ran but could not answer (step limit, model refused, API error) |
| `2` | Bad invocation (missing API key, directory does not exist) |

## Cost and privacy

- You pay for your own API usage. A typical question costs a few cents; the final line
  of output shows the token counts so you can see what each question cost.
- **File contents are sent to the Anthropic API.** `repo-ask` refuses to read files that
  commonly hold secrets (`.env*`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, ...) and
  skips `.git`, `node_modules`, virtualenvs and build output. Review
  [`workspace.py`](src/repo_ask/workspace.py) for the full list. Do not point it at a
  repository whose contents you are not allowed to share.
- It cannot read outside the directory you give it, including through symlinks.

## How it works

```
question ──▶ ┌──────────────────────────────┐
             │  model call                  │◀──────────────┐
             │  "which file should I read?" │               │
             └──────────────┬───────────────┘               │
                            │ tool call(s)                  │ tool result(s)
                            ▼                               │
             ┌──────────────────────────────┐               │
             │  read_file(path, start_line) │───────────────┘
             └──────────────────────────────┘
                            │ no more tool calls
                            ▼
                     answer with citations
```

The loop runs at most `--max-steps` times, stops if the model repeats the same call,
truncates oversized tool output, and turns every tool failure into text the model can
read and recover from. The full design is in [docs/architecture.md](docs/architecture.md).

## Development

```bash
git clone https://github.com/0xkaushik-ai/repo-ask && cd repo-ask
uv sync                 # install with dev dependencies
uv run pytest           # all tests run offline, no API key needed
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy             # strict type check
uv run repo-ask "what does config.py do?"   # try it on itself
```

See [docs/development.md](docs/development.md) for the project layout, how to add a tool,
and how the test doubles work. Contributions are welcome; read
[CONTRIBUTING.md](CONTRIBUTING.md) first.

## Roadmap

| Version | Adds | Harness concept |
|---|---|---|
| **0.1** (now) | Agent loop, `read_file`, safety sandbox, CLI | Loop, tools, error-as-information |
| 0.2 | `list_dir`, `grep` with result caps | Tool design, output truncation |
| 0.3 | Benchmark of questions with known answers | Evals |
| 0.4 | Context compaction for long sessions | Context engineering |
| 0.5 | PyPI release | Shipping |

## License

[MIT](LICENSE)
