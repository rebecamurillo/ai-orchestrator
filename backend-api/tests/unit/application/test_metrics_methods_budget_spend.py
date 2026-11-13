"""Budget and spend methods (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.methods import REGISTRY, budget, spend
from tests.unit.application.metrics_builders import (
    make_ai,
    make_attempt,
    make_inputs,
    make_row,
    make_run,
)


def test_an_uncapped_run_reads_na_for_both_budget_figures() -> None:
    inputs = make_inputs([make_row()], [])
    assert budget.budget_set(inputs)[0].missing == "n/a — no budget set"
    assert budget.budget_used(inputs)[0].missing == "n/a — no budget set"


def test_a_zero_budget_reads_na_instead_of_dividing() -> None:
    inputs = make_inputs([make_row()], [], run=make_run(budget_usd=Decimal(0)))
    assert budget.budget_used(inputs)[0].value_num is None


def test_budget_used_is_the_gate_figure_over_the_budget() -> None:
    run = make_run(budget_usd=Decimal(10), gate_spend_usd=Decimal(4))
    inputs = make_inputs([make_row()], [], run=run)
    assert budget.budget_set(inputs)[0].value_num == Decimal(10)
    assert budget.budget_used(inputs)[0].value_num == Decimal("0.4")


def test_recorded_spend_reads_the_attempt_figure_or_not_recorded() -> None:
    row = make_row()
    paid = make_ai(row, make_attempt(row, 1, cost_usd=Decimal(2)))
    free = make_ai(row, make_attempt(row, 2))
    values = spend.recorded(make_inputs([row], [paid, free]))
    run = next(v for v in values if v.scope_type == "run")
    assert (run.value_num, run.missing, run.partial_n, run.partial_m) == (
        Decimal(2),
        "partial",
        1,
        2,
    )
    assert {v.missing for v in values if v.scope_key.endswith("#2")} == {"not recorded"}


def test_project_figures_are_not_run_values() -> None:
    inputs = make_inputs([make_row()], [])
    for key in ("spend.month@1", "spend.month_cancelled@1", "spend.month_recorded@1"):
        assert REGISTRY[key](inputs) == []
