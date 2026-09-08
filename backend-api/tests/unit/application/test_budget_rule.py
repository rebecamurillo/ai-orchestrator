"""`budget.check` — whether a Run has spent past its budget. TDD first (AD-18)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.budget import check
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def a_run(*, spend_usd: Decimal, budget_usd: Decimal) -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=budget_usd,
        spend_usd=spend_usd,
        created_at=NOW,
    )


def test_a_run_over_budget_parks_with_the_figures_in_the_reason() -> None:
    run = a_run(spend_usd=Decimal("41.20"), budget_usd=Decimal("40.00"))

    park = check(run)

    assert park is not None
    assert park.kind == "budget"
    assert park.reason == "budget $41.20 / $40.00"
    assert park.path is None


def test_the_reason_always_renders_two_decimal_places() -> None:
    """A real Gateway sum can carry more precision than a park reason should show."""
    run = a_run(spend_usd=Decimal("41.203891"), budget_usd=Decimal("40.00"))

    park = check(run)

    assert park is not None
    assert park.reason == "budget $41.20 / $40.00"


def test_a_run_exactly_at_budget_does_not_park() -> None:
    run = a_run(spend_usd=Decimal("41.20"), budget_usd=Decimal("41.20"))

    assert check(run) is None


def test_a_run_at_zero_over_zero_does_not_park() -> None:
    run = a_run(spend_usd=Decimal("40.00"), budget_usd=Decimal("40.00"))

    assert check(run) is None


def test_a_run_under_budget_does_not_park() -> None:
    run = a_run(spend_usd=Decimal("10.00"), budget_usd=Decimal("40.00"))

    assert check(run) is None
