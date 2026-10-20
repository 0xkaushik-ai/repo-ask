# Architecture

`repo-ask` is an **agent harness**: the code around a language model that turns
"predict the next token" into "answer a question about this codebase". This document
explains each part, why it exists, and what would go wrong without it.

If you are learning harness engineering, read this alongside the source. Every section
names the file it describes.

## The one-sentence model

A language model is a stateless function from text to text. It has no memory, no file
access and no way to act. Everything that looks like memory, tool use or agency is the
harness feeding it the right text and executing what it writes.

```
                   ┌─────────────────────────────────────────────┐
                   │                   Agent                     │
  question ──────▶ │  messages ──▶ ModelClient ──▶ ModelResponse │
                   │       ▲                           │         │
                   │       │ tool_result blocks        │ tool    │
                   │       │                           ▼ calls   │
                   │  ToolRegistry ──▶ Tool.run(Workspace, ...)  │
                   └─────────────────────────────────────────────┘
                                       │ events
                                       ▼
                                 CLI (rich) / tests
```

## Modules

### `agent.py`: the loop

```python
messages = [question]
for step in 1..max_steps:
    response = model.complete(system, messages, tools)
    messages.append(assistant turn)          # replayed verbatim
    if no tool calls: yield Answer; return
    for call in response.tool_calls:
        output, is_error = execute(call)     # never raises
        results.append(tool_result block)
    messages.append(user turn with ALL results)
    if stuck: yield Failure; return
yield Failure("step limit")
```

Design decisions:

- **The loop never crashes.** `_execute` catches `ToolError` (expected failures, message
  goes to the model), and any other exception (logged, generic message goes to the
  model). A harness that crashes on a bad tool argument wastes every token spent so far.
- **Errors are information.** Failed calls go back with `is_error: True` and a message
  that says what to do instead ("File not found: x. Did you mean..."). Models recover
  well from errors they can read.
- **All results for one turn go back in one user message.** The API allows several tool
  calls per assistant turn. Splitting the results across messages silently teaches the
  model to stop making parallel calls.
- **Hard step cap.** `max_steps` bounds cost and time. Without it a confused model can
  loop until the context window fills.
- **Stuck detection.** The same `(tool, args)` three times in a row ends the run. This
  catches the most common infinite loop cheaply.
- **Events, not prints.** `run()` yields `ToolCallEvent`, `ToolResultEvent`, `AnswerEvent`
  and `FailureEvent`. The CLI renders them; tests assert on them. The loop knows nothing
  about terminals.

The system prompt lives here too. It explains *how to work* (locate, read, stop) and
*how to answer* (cite `path:line`, say when the answer is not in the repo). It explains
reasons, not just rules, because models generalise from reasons.

### `model.py`: the model boundary

The loop talks to a `ModelClient` protocol with one method, `complete()`. The only
implementation today is `AnthropicModel`. This boundary is what makes the loop testable:
`tests/fake_model.py` is a scripted client that returns canned responses and records
every request, so the full loop runs in milliseconds with no network.

`ModelResponse` carries both the parsed view (`text`, `tool_calls`) and the provider's
`raw_content`, which is replayed unchanged as the next assistant turn. The API requires
this: it may include blocks (such as thinking) that must round-trip intact.

The adapter also:

- Checks credentials at construction so a missing key fails before any work is done.
- Maps SDK exceptions to `ModelError` with user-facing messages, most specific first
  (authentication, not-found, rate limit, other HTTP, network).
- Surfaces `stop_reason == "refusal"` as a failure with the model's explanation.
- Uses streaming with `get_final_message()` so long inputs do not hit HTTP timeouts.

### `tools/`: the agent's hands

A tool is a `ToolSpec` (name, description, JSON schema) plus a `run()` method. **The spec
is the entire interface the model sees.** It never sees the implementation, so the
description must say what the tool does, when to use it, what comes back and what it
cannot do.

`read_file` is designed as an *agent-computer interface*, not a file reader:

- Output is line-numbered so the model can cite `path:line`.
- At most 300 lines per call, with a footer: `[N more lines. Call again with start_line=M]`.
  The model learns pagination from the output itself.
- Binary files, directories, missing files and out-of-range lines each produce a
  distinct, actionable error.
- Arguments are validated (`start_line` must be a positive integer) because models
  occasionally send strings for numbers.

`truncate()` caps any tool result at `max_tool_result_chars`. One oversized result can
otherwise consume the context window and every later call pays for it.

`ToolRegistry` holds tools by name, rejects duplicates, and produces the `tools=[...]`
list for the API.

### `workspace.py`: the sandbox

All filesystem access goes through `Workspace.resolve()`. It rejects:

- absolute paths and `..` escapes (resolved path must be inside the root);
- symlinks that point outside the root (checked after `resolve()`);
- ignored directories (`.git`, `node_modules`, virtualenvs, caches, build output);
- files that commonly hold secrets (`.env*`, `*.pem`, `*.key`, `id_rsa`, ...).

The tool is read-only, but file contents are sent to a third-party API, so "what can be
read" is a privacy boundary. Keeping it in one class makes it auditable and testable in
isolation (`tests/test_workspace.py`).

### `config.py`: settings

Every tunable number lives in `Settings`: model, step cap, output tokens, effort, result
truncation. Resolution order is CLI flag > `REPO_ASK_*` environment variable > default.
Nothing in the loop or the tools hard-codes a limit.

### `cli.py`: presentation

Parses arguments, builds the objects, iterates events. Progress goes to stderr and the
answer to stdout so `repo-ask "q" > out.md` captures only the answer. Exit codes:
0 answered, 1 ran but failed, 2 bad invocation.

## Data flow for one question

```
1. user:      "what does main return?"
2. assistant: tool_use read_file(path="src/app.py")        ← step 1
3. user:      tool_result "src/app.py (lines 1-5 of 5)\n1| import os ..."
4. assistant: "It returns 42 (src/app.py:5)."              ← step 2, no tool calls → done
```

Each model call re-sends the whole list. That is why tool output size matters: a 50 KB
result in message 3 is paid for again in every later call.

## What is deliberately not here (yet)

| Missing | Why | Planned |
|---|---|---|
| `grep` / `list_dir` | Milestone 1 proves the loop; search tools come next | 0.2 |
| Context compaction | Questions rarely exceed the window today | 0.4 |
| Sub-agents | No need until searches get large | later |
| Write / shell tools | Read-only is the safety story of this tool | not planned |
| Multiple providers | One adapter keeps v1 small; the protocol makes adding one cheap | maybe |
| Framework (LangChain etc.) | The point is to see the loop, not hide it | never |

## Testing strategy

| Layer | Test file | Double used |
|---|---|---|
| Sandbox rules | `test_workspace.py` | real temp directory |
| Tool behaviour and error text | `test_read_file.py` | real temp directory |
| Loop control flow | `test_agent.py` | `FakeModel` (scripted responses) |
| SDK adapter | `test_model.py` | stub client, real SDK response types |

Everything runs offline. Live calls are exercised manually and, from 0.3, by the
benchmark.
