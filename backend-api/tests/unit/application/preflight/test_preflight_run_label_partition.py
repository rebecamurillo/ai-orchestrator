"""`checks.run_label` prefers `partition_branch` over `worktrees[0].branch` (story 5-1).

The key correctness claim: when `partition_branch` is set, the label shows the declared
branch (what the Operator wrote), not the allocated fresh name (what the engine created).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.preflight.checks import run_label
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "inputs": {},
        "budget_usd": Decimal("0"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


# ── partition_branch takes precedence over worktrees[0].branch ───────────────


def test_run_label_uses_partition_branch_when_set_over_worktree_allocated_branch() -> None:
    """run_label shows the declared branch, not the allocated (fresh) worktree name."""
    run = a_run(
        partition_branch="feat/s",
        worktrees=(Worktree(branch="feat/s-1", path="/work/x", created_branch=True, pushed=False),),
    )

    assert run_label(run) == "epic · feat/s"


def test_run_label_falls_back_to_worktree_when_partition_branch_is_none() -> None:
    """When partition_branch is None (old run), the first worktree branch is used."""
    run = a_run(
        partition_branch=None,
        worktrees=(Worktree(branch="feat/s-1", path="/work/x", created_branch=True, pushed=False),),
    )

    assert run_label(run) == "epic · feat/s-1"
