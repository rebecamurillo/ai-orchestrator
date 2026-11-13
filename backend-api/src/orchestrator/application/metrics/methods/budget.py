"""Part A budget methods: the budget set and the share the budget gate's figure used."""

from __future__ import annotations

from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.values import MetricValue, na, number, word
from orchestrator.application.rules.budget import figure

NO_BUDGET = na("no budget set")


@register("budget.set@1")
def budget_set(inputs: RunInputs) -> list[MetricValue]:
    budget = inputs.run.budget_usd
    if budget is None:
        return [word("budget.set", "run", "run", NO_BUDGET, unit="USD")]
    return [number("budget.set", "run", "run", budget, unit="USD")]


@register("budget.used@1")
def budget_used(inputs: RunInputs) -> list[MetricValue]:
    budget = inputs.run.budget_usd
    if budget is None or budget == 0:
        return [word("budget.used", "run", "run", NO_BUDGET, unit="ratio")]
    return [number("budget.used", "run", "run", figure(inputs.run) / budget, unit="ratio")]
