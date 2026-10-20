"""Runtime settings for the agent.

Everything tunable lives here so the loop, the tools and the CLI never hard-code
numbers. Values come from (highest priority first): CLI flags, environment
variables, then the defaults below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    # Hard cap on model calls per question. Protects against runaway loops.
    max_steps: int = 25
    # Max output tokens per model call.
    max_output_tokens: int = 16_000
    # Reasoning depth. Lower is cheaper and faster.
    effort: str = "medium"
    # Any single tool result larger than this is truncated before the model sees it.
    max_tool_result_chars: int = 40_000

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from REPO_ASK_* environment variables, falling back to defaults."""
        defaults = cls()
        return cls(
            model=os.environ.get("REPO_ASK_MODEL", defaults.model),
            max_steps=int(os.environ.get("REPO_ASK_MAX_STEPS", defaults.max_steps)),
            max_output_tokens=int(
                os.environ.get("REPO_ASK_MAX_OUTPUT_TOKENS", defaults.max_output_tokens)
            ),
            effort=os.environ.get("REPO_ASK_EFFORT", defaults.effort),
            max_tool_result_chars=int(
                os.environ.get("REPO_ASK_MAX_TOOL_RESULT_CHARS", defaults.max_tool_result_chars)
            ),
        )
