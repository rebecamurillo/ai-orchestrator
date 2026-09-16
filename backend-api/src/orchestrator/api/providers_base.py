"""The `app.state` attribute names, and the accessors every provider module reads them with.

Split out of `api/providers.py` when it crossed the 400-line cap (`test_source_limits.py`):
the split-not-trim rule says a capped module gains a sibling, and the sibling every feature
provider needs is this one — the constants and accessors live below both `providers.py` and
its feature siblings (`providers_run_files.py`, `providers_trajectories.py`), so no two of
them ever import each other in a cycle.

Nothing here asserts. `python -O` strips `assert`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from orchestrator.domain.ports.git import Git

#: The attributes `create_app` stores its adapters under.
SESSION_FACTORY = "session_factory"
CRYPTO = "crypto"
GIT = "git"
ENGINE = "engine"
SETTINGS = "settings"


def from_state(request: Request, attribute: str) -> Any:
    """One adapter off `app.state`, or a failure that says which one is missing."""
    value = getattr(request.app.state, attribute, None)
    if value is None:
        raise RuntimeError(
            f"app.state.{attribute} is not set: this application was built without it, "
            "and only main() wires the adapters"
        )
    return value


def git_adapter(request: Request) -> Git | None:
    """The git adapter, read tolerantly rather than through `from_state`.

    Every other adapter here is required, because no route can answer without it. This one
    is not: an application built without it still serves every Project and Repository
    operation, and only the clone check needs it — which then refuses loudly, naming the
    port, rather than this dependency refusing a read that never touches git.
    """
    adapter: Git | None = getattr(request.app.state, GIT, None)
    return adapter


def required_git(request: Request, needed_by: str) -> Git:
    """`git_adapter`, refusing loudly by name — pre-flight and `create_run` both need it."""
    git = git_adapter(request)
    if git is None:
        raise RuntimeError(
            f"app.state.git is not set: this application was built without it, "
            f"and {needed_by} needs a git port"
        )
    return git
