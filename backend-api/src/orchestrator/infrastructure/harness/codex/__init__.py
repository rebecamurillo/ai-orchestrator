"""The Codex CLI adapter (AD-10). One harness, one package, one invocation.

`adapter.py` writes the command line; `events.py` reads the `--json` stream back. Every name
either of them defines for the CLI itself is provisional until story 7.2 has run the real
binary — see `adapter.py`'s own docstring and `addendum.md` §B.
"""

from __future__ import annotations

from orchestrator.infrastructure.harness.codex.adapter import (
    CODEX_HOME,
    CodexHarness,
    codex_aliases,
)
from orchestrator.infrastructure.harness.codex.events import (
    result_object,
    session_id_from,
    usage_from,
)

__all__ = [
    "CODEX_HOME",
    "CodexHarness",
    "codex_aliases",
    "result_object",
    "session_id_from",
    "usage_from",
]
