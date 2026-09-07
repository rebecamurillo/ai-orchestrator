"""Harness adapters and the environment they all receive (AD-10, AD-5).

`env.py` is shared by every adapter — the contract `scripts/harness/_common.sh` declares —
and each harness gets its own subpackage for the one thing that is its own: the invocation
and the native names it derives from the contract. Epic 7 adds `codex/` and `local/` beside
`claude/` and changes nothing here but this file's imports.
"""

from __future__ import annotations

from orchestrator.infrastructure.harness.claude import ClaudeHarness, claude_aliases
from orchestrator.infrastructure.harness.env import HARNESS_ENV_CONTRACT, env_for

__all__ = ["HARNESS_ENV_CONTRACT", "ClaudeHarness", "claude_aliases", "env_for"]
