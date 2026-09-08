"""`budget.forced` — the unconditional park for the harness's own cap exit (5.7). TDD
first (AD-18)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.budget import forced
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


def test_forced_parks_even_when_spend_is_under_budget() -> None:
    """The harness's own cap already stopped it; the figures are reported regardless of
    what the ordinary comparison would say."""
    run = a_run(spend_usd=Decimal("5.00"), budget_usd=Decimal("40.00"))

    park = forced(run)

    assert park.kind == "budget"
    assert park.reason == "budget $5.00 / $40.00"
    assert park.path is None


def test_forced_renders_the_same_two_decimal_reason_check_does() -> None:
    run = a_run(spend_usd=Decimal("41.203891"), budget_usd=Decimal("40.00"))

    assert forced(run).reason == "budget $41.20 / $40.00"
