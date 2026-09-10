"""The OpenCode CLI adapter, registered as `local` (AD-10). One harness, one package.

`adapter.py` writes the command line; `events.py` reads the `--format json` stream back;
`sessions.py` is the session-store fallback for a run that printed no session of its own. Every
name any of them defines for the CLI itself is provisional until story 7.4 has run the real
binary against a real local model server — see `adapter.py`'s own docstring and `addendum.md` §B.
"""

from __future__ import annotations

from orchestrator.infrastructure.harness.opencode.adapter import (
    LANGFUSE_BASE_URL_ALIAS,
    LANGFUSE_USER_ID_ALIAS,
    LocalHarness,
    local_aliases,
)
from orchestrator.infrastructure.harness.opencode.events import (
    result_object,
    session_id_from,
    usage_from,
)
from orchestrator.infrastructure.harness.opencode.sessions import (
    session_for_directory,
    store_path,
)

__all__ = [
    "LANGFUSE_BASE_URL_ALIAS",
    "LANGFUSE_USER_ID_ALIAS",
    "LocalHarness",
    "local_aliases",
    "result_object",
    "session_for_directory",
    "session_id_from",
    "store_path",
    "usage_from",
]
