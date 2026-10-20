# Development guide

## Setup

```bash
git clone https://github.com/0xkaushik-ai/repo-ask && cd repo-ask
uv sync                      # Python 3.11+, creates .venv with dev dependencies
uv run pytest                # should pass with no API key and no network
```

Run the tool from source:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run repo-ask "what does the agent loop do?"
```

## Checks

These are what CI runs. All three must pass before a pull request is merged.

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

`ruff format .` fixes formatting in place.

## Project layout

```
src/repo_ask/
  __init__.py      version
  agent.py         the loop, system prompt, events
  cli.py           argument parsing and terminal output
  config.py        Settings (defaults, env overrides)
  model.py         ModelClient protocol + AnthropicModel adapter
  workspace.py     path sandbox and ignore/secret rules
  tools/
    __init__.py    ToolRegistry, default_tools()
    base.py        Tool, ToolSpec, ToolError, truncate()
    read_file.py   the read_file tool
tests/
  conftest.py      `repo` and `workspace` fixtures (a tiny project in a temp dir)
  fake_model.py    FakeModel + tool_turn()/answer_turn() helpers
  test_*.py        one file per module
docs/              you are here
```

## Adding a tool

1. Create `src/repo_ask/tools/<name>.py` with a class that extends `Tool`.
2. Write the `ToolSpec` first. The description is the whole interface the model sees:
   say what the tool does, when to use it, what the output looks like, and its limits.
   Use `"additionalProperties": False` and list `required` fields in the schema.
3. Implement `run(self, workspace, **kwargs)`:
   - validate every argument yourself; raise `ToolError("...")` with a message that tells
     the model what to do instead;
   - resolve paths only through `workspace.resolve()`;
   - cap the output size (lines, matches) and say in the output when it was capped;
   - return plain text.
4. Register it in `default_tools()` in `tools/__init__.py`.
5. Add `tests/test_<name>.py`. Cover the happy path, every error message, and the cap.
6. Add a loop test in `test_agent.py` if the tool changes how the agent behaves.

A tool must never raise anything other than `ToolError` on purpose. The loop catches
other exceptions, but they are logged as bugs.

## Testing without the API

`tests/fake_model.py` provides a scripted `ModelClient`:

```python
model = FakeModel(
    [
        tool_turn(("read_file", {"path": "src/app.py"})),  # first call: ask for a tool
        answer_turn("It returns 42 (src/app.py:5)."),  # second call: answer
    ]
)
events = list(Agent(model=model, tools=default_tools(), workspace=ws).run("question"))
model.requests[1]["messages"]  # exactly what the loop sent on the second call
```

Use it to assert on the *conversation the loop builds*, not just the final answer. Most
harness bugs are in message construction.

For the SDK adapter, `tests/test_model.py` builds real `anthropic.types.Message` objects
and feeds them through a stub client, so parsing is tested against the real types.

## Trying a change against a real repo

```bash
uv run repo-ask "where is the entry point?" -C ~/some/project --verbose
```

`--verbose` prints every tool result in full. Read the trace: when the agent does
something odd, ask what it could see at that moment. Usually a tool description or an
error message was unclear, and that is the thing to fix.

## Releasing

Not yet. Version is in `pyproject.toml` and `src/repo_ask/__init__.py`; keep them in sync.
