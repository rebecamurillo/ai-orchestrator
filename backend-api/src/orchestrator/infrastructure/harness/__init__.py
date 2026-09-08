"""Harness adapters and the environment they all receive (AD-10, AD-5).

`env.py` is shared by every adapter — the contract `scripts/harness/_common.sh` declares —
and each harness gets its own subpackage for the one thing that is its own: the invocation
and the native names it derives from the contract. `registry.py` is where the two are
joined into the two things a composition root wires: the registry a Template's `harness:`
resolves through, and the environment builder one attempt's process receives. Epic 7 adds
`codex/` and `local/` beside `claude/` and changes nothing here but this file's imports.
"""

from __future__ import annotations

from orchestrator.infrastructure.harness.claude import ClaudeHarness, claude_aliases
from orchestrator.infrastructure.harness.env import HARNESS_ENV_CONTRACT, env_for
from orchestrator.infrastructure.harness.registry import (
    ALIASES,
    build_harness_env,
    build_harnesses,
)

__all__ = [
    "ALIASES",
    "HARNESS_ENV_CONTRACT",
    "ClaudeHarness",
    "build_harness_env",
    "build_harnesses",
    "claude_aliases",
    "env_for",
]
