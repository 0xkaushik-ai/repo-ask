"""Command-line entry point: `repo-ask "your question"`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from repo_ask import __version__
from repo_ask.agent import Agent, AnswerEvent, FailureEvent, ToolCallEvent, ToolResultEvent
from repo_ask.config import Settings
from repo_ask.model import AnthropicModel, ModelError
from repo_ask.tools import default_tools
from repo_ask.workspace import Workspace, WorkspaceError

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    defaults = Settings.from_env()
    parser = argparse.ArgumentParser(
        prog="repo-ask",
        description="Ask questions about a codebase. Read-only: never edits files or runs code.",
        epilog=(
            "Requires ANTHROPIC_API_KEY in the environment. "
            "Environment overrides: REPO_ASK_MODEL, REPO_ASK_MAX_STEPS, REPO_ASK_EFFORT."
        ),
    )
    parser.add_argument("question", help="The question to answer, in quotes.")
    parser.add_argument(
        "-C", "--root", default=".", help="Project directory to read (default: current directory)."
    )
    parser.add_argument(
        "--model", default=defaults.model, help=f"Model ID (default: {defaults.model})."
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=defaults.max_steps,
        help=f"Max model calls per question (default: {defaults.max_steps}).",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default=defaults.effort,
        help=f"Reasoning effort; lower is cheaper (default: {defaults.effort}).",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Print only the final answer.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full tool output.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, stream=sys.stderr)
    console = Console()
    status = Console(stderr=True)

    try:
        workspace = Workspace(Path(args.root))
    except WorkspaceError as exc:
        status.print(f"[red]error:[/red] {exc}")
        return EXIT_USAGE

    settings = Settings(
        model=args.model,
        max_steps=args.max_steps,
        effort=args.effort,
    )
    try:
        model = AnthropicModel(settings)
    except ModelError as exc:
        status.print(f"[red]error:[/red] {exc}")
        return EXIT_USAGE
    agent = Agent(
        model=model,
        tools=default_tools(),
        workspace=workspace,
        settings=settings,
    )

    for event in agent.run(args.question):
        match event:
            case ToolCallEvent(step=step, call=call):
                if not args.quiet:
                    arg_text = ", ".join(f"{k}={v!r}" for k, v in call.input.items())
                    status.print(f"[dim]{step:>2}[/dim] [cyan]{call.name}[/cyan]({arg_text})")
            case ToolResultEvent(output=output, is_error=is_error):
                if is_error and not args.quiet:
                    status.print(f"   [yellow]↳ {output.splitlines()[0]}[/yellow]")
                elif args.verbose:
                    status.print(f"[dim]{output}[/dim]")
            case AnswerEvent(text=text, steps=steps, usage=usage):
                if not args.quiet:
                    status.print()
                console.print(Markdown(text))
                if not args.quiet:
                    status.print(
                        f"\n[dim]{steps} steps · {usage.input_tokens:,} in / "
                        f"{usage.output_tokens:,} out tokens[/dim]"
                    )
                return EXIT_OK
            case FailureEvent(reason=reason):
                status.print(f"[red]failed:[/red] {reason}")
                return EXIT_FAILED
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
