"""`budget.figure` is the one spend every budget comparison uses (story 5, owner decision T4,
2026-11-12; RM-4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.rules import budget
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id


def a_run(*, spend: str, gate: str, budget_usd: str | None = "10.25") -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal(budget_usd) if budget_usd else None,
        spend_usd=Decimal(spend),
        gate_spend_usd=Decimal(gate),
        created_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
    )


def test_the_figure_is_the_gate_spend() -> None:
    assert budget.figure(a_run(spend="1", gate="7")) == Decimal("7")


def test_a_gate_above_budget_parks_while_spend_is_below() -> None:
    park = budget.check(a_run(spend="9", gate="10.50"))

    assert park is not None
    assert park.kind == "budget"
    assert park.reason == "budget $10.50 / $10.25"


def test_spend_above_budget_with_the_gate_below_does_not_park() -> None:
    assert budget.check(a_run(spend="50", gate="3")) is None


def test_forced_renders_the_gate_figure_in_both_reason_forms() -> None:
    assert budget.forced(a_run(spend="1", gate="10.5")).reason == "budget $10.50 / $10.25"
    assert (
        budget.forced(a_run(spend="1", gate="2", budget_usd=None)).reason
        == "budget $2.00 / (no cap)"
    )
