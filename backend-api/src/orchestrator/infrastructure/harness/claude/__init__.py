"""The Claude Code adapter (AD-10). One harness, one package, one invocation."""

from __future__ import annotations

from orchestrator.infrastructure.harness.claude.adapter import ClaudeHarness
from orchestrator.infrastructure.harness.claude.aliases import (
    SUBSCRIPTION_KEY_HEADER,
    claude_aliases,
    claude_native_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.claude.result import (
    json_objects,
    read_text,
    result_object,
    usage_from,
)

__all__ = [
    "SUBSCRIPTION_KEY_HEADER",
    "ClaudeHarness",
    "claude_aliases",
    "claude_native_aliases",
    "claude_subscription_aliases",
    "json_objects",
    "read_text",
    "result_object",
    "usage_from",
]
