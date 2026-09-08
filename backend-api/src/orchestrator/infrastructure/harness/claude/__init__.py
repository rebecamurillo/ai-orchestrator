"""The Claude Code adapter (AD-10). One harness, one package, one invocation."""

from __future__ import annotations

from orchestrator.infrastructure.harness.claude.adapter import ClaudeHarness, claude_aliases
from orchestrator.infrastructure.harness.claude.result import (
    json_objects,
    read_text,
    result_object,
    usage_from,
)

__all__ = [
    "ClaudeHarness",
    "claude_aliases",
    "json_objects",
    "read_text",
    "result_object",
    "usage_from",
]
