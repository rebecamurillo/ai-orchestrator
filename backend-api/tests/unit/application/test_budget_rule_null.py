"""`budget.check` — null-budget run: spend at any value never parks (story 3-2)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.budget import check, forced
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def a_null_budget_run(*, spend_usd: Decimal) -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=None,
        spend_usd=spend_usd,
        created_at=NOW,
    )


def test_null_budget_run_does_not_park_at_zero_spend() -> None:
    run = a_null_budget_run(spend_usd=Decimal("0"))
    assert check(run) is None


def test_null_budget_run_does_not_park_at_large_spend() -> None:
    run = a_null_budget_run(spend_usd=Decimal("9999.99"))
    assert check(run) is None


def test_forced_on_null_budget_run_reports_spend_only() -> None:
    """Defensive path: harness exited for a non-budget reason on an uncapped run."""
    run = a_null_budget_run(spend_usd=Decimal("12.34"))
    park = forced(run)
    assert park.kind == "budget"
    assert park.reason == "budget $12.34 / (no cap)"
