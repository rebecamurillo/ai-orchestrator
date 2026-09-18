"""`HeaderMetaOut.model` — the wire field for the dispatching model (story 1-4, FR-11).

Written first (TDD, AD-18): must fail before `Header.model` and `HeaderMetaOut.model`
are added and `HeaderOut.of()` is updated to wire the field through.

Cannot be added to `test_run_view_schemas.py` because that file is frozen (AGENTS.md rule 1).
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.api.schemas.run_views import HeaderOut
from orchestrator.application.use_cases.run_view_types import Header

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_header_meta_out_carries_model_when_set() -> None:
    """HeaderOut.of() projects Header.model onto HeaderMetaOut.model."""
    header = Header(
        project="Acme",
        repository="acme-app",
        base_branch="main",
        folder="specs",
        template="repo-init",
        version=1,
        harness="claude",
        model="claude-opus-5",
        started_at=None,
        worktree_path=None,
    )
    out = HeaderOut.of(header)
    assert out.meta.model == "claude-opus-5"


def test_header_meta_out_model_is_none_when_absent() -> None:
    """HeaderMetaOut.model is null (None) when the run had no model input."""
    header = Header(
        project="Acme",
        repository="acme-app",
        base_branch="main",
        folder="specs",
        template="repo-init",
        version=1,
        harness=None,
        model=None,
        started_at=None,
        worktree_path=None,
    )
    out = HeaderOut.of(header)
    assert out.meta.model is None
