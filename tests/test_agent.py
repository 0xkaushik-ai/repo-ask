from __future__ import annotations

from typing import Any

from fake_model import FakeModel, answer_turn, tool_turn

from repo_ask.agent import (
    Agent,
    AgentEvent,
    AnswerEvent,
    FailureEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from repo_ask.config import Settings
from repo_ask.model import ModelResponse, Usage
from repo_ask.tools import ToolRegistry, default_tools
from repo_ask.tools.base import Tool, ToolSpec
from repo_ask.workspace import Workspace


def run(model: FakeModel, workspace: Workspace, **settings: Any) -> list[AgentEvent]:
    agent = Agent(
        model=model, tools=default_tools(), workspace=workspace, settings=Settings(**settings)
    )
    return list(agent.run("what does main return?"))


def test_answers_after_reading_a_file(workspace: Workspace) -> None:
    model = FakeModel(
        [
            tool_turn(("read_file", {"path": "src/app.py"})),
            answer_turn("It returns 42 (src/app.py:5)."),
        ]
    )

    events = run(model, workspace)

    assert isinstance(events[0], ToolCallEvent)
    assert isinstance(events[1], ToolResultEvent)
    assert not events[1].is_error
    assert "5|     return 42" in events[1].output
    assert events[-1] == AnswerEvent(
        text="It returns 42 (src/app.py:5).", steps=2, usage=Usage(20, 10)
    )

    # The second request must carry the full history: question, tool_use, tool_result.
    second = model.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    result_block = second[2]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "call_0"
    assert result_block["is_error"] is False


def test_tool_error_is_sent_back_not_raised(workspace: Workspace) -> None:
    model = FakeModel(
        [tool_turn(("read_file", {"path": "missing.py"})), answer_turn("No such file.")]
    )

    events = run(model, workspace)

    result = events[1]
    assert isinstance(result, ToolResultEvent) and result.is_error
    assert "not found" in result.output
    assert model.requests[1]["messages"][2]["content"][0]["is_error"] is True
    assert isinstance(events[-1], AnswerEvent)


def test_unknown_tool_is_reported_to_model(workspace: Workspace) -> None:
    model = FakeModel([tool_turn(("run_shell", {"cmd": "rm -rf /"})), answer_turn("ok")])

    events = run(model, workspace)

    result = events[1]
    assert isinstance(result, ToolResultEvent) and result.is_error
    assert "Unknown tool 'run_shell'" in result.output
    assert "read_file" in result.output


def test_crashing_tool_does_not_crash_loop(workspace: Workspace) -> None:
    class Boom(Tool):
        spec = ToolSpec(name="boom", description="explodes", input_schema={"type": "object"})

        def run(self, workspace: Workspace, **kwargs: Any) -> str:
            raise RuntimeError("kaboom")

    model = FakeModel([tool_turn(("boom", {})), answer_turn("survived")])
    agent = Agent(model=model, tools=ToolRegistry([Boom()]), workspace=workspace)

    events = list(agent.run("q"))

    assert isinstance(events[1], ToolResultEvent) and events[1].is_error
    assert "failed unexpectedly" in events[1].output
    assert isinstance(events[-1], AnswerEvent)


def test_parallel_tool_calls_return_in_one_message(workspace: Workspace) -> None:
    model = FakeModel(
        [
            tool_turn(("read_file", {"path": "src/app.py"}), ("read_file", {"path": "README.md"})),
            answer_turn("done"),
        ]
    )

    events = run(model, workspace)

    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 2
    blocks = model.requests[1]["messages"][2]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["call_0", "call_1"]


def test_step_limit_stops_the_loop(workspace: Workspace) -> None:
    calls = [tool_turn(("read_file", {"path": f"f{i}.py"})) for i in range(10)]
    model = FakeModel(calls)

    events = run(model, workspace, max_steps=3)

    failure = events[-1]
    assert isinstance(failure, FailureEvent)
    assert "step limit (3)" in failure.reason
    assert len(model.requests) == 3


def test_repeated_identical_calls_are_detected(workspace: Workspace) -> None:
    same = ("read_file", {"path": "src/app.py"})
    model = FakeModel([tool_turn(same), tool_turn(same), tool_turn(same), answer_turn("never")])

    events = run(model, workspace)

    failure = events[-1]
    assert isinstance(failure, FailureEvent)
    assert "repeated" in failure.reason
    assert len(model.requests) == 3


def test_long_tool_output_is_truncated(workspace: Workspace) -> None:
    class Loud(Tool):
        spec = ToolSpec(name="loud", description="talks a lot", input_schema={"type": "object"})

        def run(self, workspace: Workspace, **kwargs: Any) -> str:
            return "x" * 10_000

    model = FakeModel([tool_turn(("loud", {})), answer_turn("ok")])
    agent = Agent(
        model=model,
        tools=ToolRegistry([Loud()]),
        workspace=workspace,
        settings=Settings(max_tool_result_chars=100),
    )

    events = list(agent.run("q"))

    output = events[1].output  # type: ignore[union-attr]
    assert output.startswith("x" * 100)
    assert "truncated 9900 characters" in output


def test_refusal_becomes_failure(workspace: Workspace) -> None:
    refusal = ModelResponse(
        text="", tool_calls=[], stop_reason="refusal", raw_content=[], refusal_explanation="policy"
    )
    events = run(FakeModel([refusal]), workspace)
    assert events == [FailureEvent(reason="policy", steps=1, usage=Usage())]


def test_system_prompt_and_tools_are_sent(workspace: Workspace) -> None:
    model = FakeModel([answer_turn("hi")])
    run(model, workspace)
    request = model.requests[0]
    assert "repo-ask" in request["system"]
    assert [t["name"] for t in request["tools"]] == ["read_file"]
