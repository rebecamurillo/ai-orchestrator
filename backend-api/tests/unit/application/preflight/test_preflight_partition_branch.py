"""`preflight/checks._holding_run` (story 5-1, AD-12): the branch-partition check that
decides whether another run holds the (repository, declared-branch) slot.

Three cases: match, no-match, and None partition_branch on the candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.preflight.checks import _holding_run
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def a_repository() -> Repository:
    return Repository(
        id=new_id(),
        project_id=new_id(),
        slug="repo",
        url="https://example.test/org/repo.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(repository_id: object, **overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": repository_id,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "inputs": {},
        "budget_usd": Decimal("0"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


# ── _holding_run returns a run when partition_branch matches ──────────────────


def test_holding_run_returns_run_when_partition_branch_matches() -> None:
    """A non-terminal run whose partition_branch equals the declared branch is the holder."""
    repository = a_repository()
    holder = a_run(repository.id, partition_branch="feat/x")

    result = _holding_run(FakeRunRepository([holder]), repository, "feat/x")

    assert result is holder


# ── _holding_run returns None when partition_branch differs ───────────────────


def test_holding_run_returns_none_when_partition_branch_differs() -> None:
    """A run on the same repository but a different branch does not hold this slot."""
    repository = a_repository()
    other = a_run(repository.id, partition_branch="feat/y")

    result = _holding_run(FakeRunRepository([other]), repository, "feat/x")

    assert result is None


# ── _holding_run returns None when candidate has no partition_branch ──────────


def test_holding_run_returns_none_when_candidate_partition_branch_is_none() -> None:
    """Old runs with partition_branch = None are treated as non-competing (story 5-1)."""
    repository = a_repository()
    old_run = a_run(repository.id, partition_branch=None)

    result = _holding_run(FakeRunRepository([old_run]), repository, "feat/x")

    assert result is None


# ── _holding_run returns None when repository is None ────────────────────────


def test_holding_run_returns_none_when_repository_is_none() -> None:
    """No repository means no slot to hold."""
    run = a_run(new_id(), partition_branch="feat/x")

    result = _holding_run(FakeRunRepository([run]), None, "feat/x")

    assert result is None
