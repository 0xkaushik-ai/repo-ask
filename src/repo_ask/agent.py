"""The agent loop.

    messages = [question]
    repeat up to max_steps:
        response = model(messages)
        if response has no tool calls: done, return the text
        run each tool, append the results, continue

Everything else in this file exists to keep that loop from crashing or spinning:
tool failures become text, unknown tools become text, repeated identical calls
are detected, and a step cap ends the run.

The loop yields `AgentEvent`s as it goes so the CLI can show progress live and
tests can assert on exactly what happened.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from repo_ask.config import Settings
from repo_ask.model import ModelClient, ModelError, ToolCall, Usage
from repo_ask.tools import ToolError, ToolRegistry, truncate
from repo_ask.workspace import Workspace

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are repo-ask, an assistant that answers questions about a software project by reading \
its files. You can only read; you cannot edit files or run commands.

How to work:
- Start by locating the relevant files, then read them. Prefer reading the actual code over \
guessing from file names.
- Read enough to be confident, but no more. Each tool call costs the user money.
- When you have the answer, stop calling tools and write it.

How to answer:
- Be concrete. Cite locations as `path:line` (for example `src/auth.py:42`) so the user can \
verify every claim.
- If the project does not contain the answer, say so plainly instead of guessing.
- Keep the answer focused on the question. No preamble.
"""

# If the model issues the same tool call this many times in a row, it is stuck.
REPEAT_CALL_LIMIT = 3


@dataclass(frozen=True)
class ToolCallEvent:
    step: int
    call: ToolCall


@dataclass(frozen=True)
class ToolResultEvent:
    step: int
    call: ToolCall
    output: str
    is_error: bool


@dataclass(frozen=True)
class AnswerEvent:
    text: str
    steps: int
    usage: Usage


@dataclass(frozen=True)
class FailureEvent:
    """The run ended without an answer. `reason` is user-facing."""

    reason: str
    steps: int
    usage: Usage


AgentEvent = ToolCallEvent | ToolResultEvent | AnswerEvent | FailureEvent


@dataclass
class Agent:
    model: ModelClient
    tools: ToolRegistry
    workspace: Workspace
    settings: Settings = field(default_factory=Settings)

    def run(self, question: str) -> Iterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        usage = Usage()
        recent_calls: list[tuple[str, str]] = []

        for step in range(1, self.settings.max_steps + 1):
            try:
                response = self.model.complete(
                    system=SYSTEM_PROMPT, messages=messages, tools=self.tools.to_api()
                )
            except ModelError as exc:
                yield FailureEvent(reason=str(exc), steps=step, usage=usage)
                return
            usage = usage + response.usage
            messages.append({"role": "assistant", "content": response.raw_content})

            if response.stop_reason == "refusal":
                reason = response.refusal_explanation or "The model declined to answer."
                yield FailureEvent(reason=reason, steps=step, usage=usage)
                return

            if not response.tool_calls:
                if response.stop_reason == "max_tokens":
                    log.warning("answer was cut off at max_output_tokens")
                yield AnswerEvent(text=response.text, steps=step, usage=usage)
                return

            results: list[dict[str, Any]] = []
            for call in response.tool_calls:
                yield ToolCallEvent(step=step, call=call)
                output, is_error = self._execute(call)
                yield ToolResultEvent(step=step, call=call, output=output, is_error=is_error)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
            # All results for one assistant turn go back in ONE user message.
            messages.append({"role": "user", "content": results})

            if self._is_stuck(recent_calls, response.tool_calls):
                yield FailureEvent(
                    reason="The agent repeated the same tool call several times and was stopped.",
                    steps=step,
                    usage=usage,
                )
                return

        yield FailureEvent(
            reason=f"Reached the step limit ({self.settings.max_steps}) without an answer. "
            "Try a narrower question or raise --max-steps.",
            steps=self.settings.max_steps,
            usage=usage,
        )

    def _execute(self, call: ToolCall) -> tuple[str, bool]:
        """Run one tool call. Never raises: every failure becomes text for the model."""
        tool = self.tools.get(call.name)
        if tool is None:
            return (
                f"Unknown tool {call.name!r}. Available tools: {', '.join(self.tools.names())}.",
                True,
            )
        try:
            output = tool.run(self.workspace, **call.input)
        except ToolError as exc:
            return str(exc), True
        except Exception:
            log.exception("tool %s crashed with input %r", call.name, call.input)
            return f"Tool {call.name!r} failed unexpectedly. Try different arguments.", True
        return truncate(output, self.settings.max_tool_result_chars), False

    @staticmethod
    def _is_stuck(recent: list[tuple[str, str]], calls: list[ToolCall]) -> bool:
        """Track the last few calls; stuck means the same call repeated REPEAT_CALL_LIMIT times."""
        for call in calls:
            recent.append((call.name, repr(sorted(call.input.items()))))
        del recent[:-REPEAT_CALL_LIMIT]
        return len(recent) == REPEAT_CALL_LIMIT and len(set(recent)) == 1
