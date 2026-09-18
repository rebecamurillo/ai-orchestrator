"""`_header()` — the Header domain value's model field (story 1-4, FR-11).

Written first (TDD, AD-18): both tests must fail before `Header.model` is added to
`run_view_types.py` and `_header()` is updated in `run_views.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.run_views import _header
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "repo-init",
        "template_version": 1,
        "inputs": {},
        "status": "queued",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def test_header_model_is_populated_from_run_inputs() -> None:
    """_header() reads model from run.inputs — EXPERIENCE-v1.md delta 26 (2026-09-15)."""
    run = _a_run(inputs={"base_branch": "main", "model": "claude-opus-5"})
    header = _header(run, None, None)
    assert header.model == "claude-opus-5"


def test_header_model_is_none_when_absent_from_inputs() -> None:
    """model is null on the wire when run.inputs has no 'model' key."""
    run = _a_run(inputs={"base_branch": "main"})
    header = _header(run, None, None)
    assert header.model is None
