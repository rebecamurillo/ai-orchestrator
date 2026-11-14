"""Part A spend methods: the per-attempt figure stored today, summed over scopes."""

from __future__ import annotations

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import Reading, sum_over_scopes
from orchestrator.application.metrics.values import NOT_RECORDED, MetricValue

TYPES = ("run", "epic", "story", "step", "attempt")


def recorded_reading(ai: AttemptInputs) -> Reading:
    cost = ai.attempt.cost_usd
    return NOT_RECORDED if cost is None else cost


@register("spend.recorded@1")
def recorded(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "spend.recorded", "USD", inputs, TYPES, recorded_reading, model_only=False
    )


def _project_scope(inputs: RunInputs) -> list[MetricValue]:
    """A project figure is not a Run value; epic 4 computes it from the Run totals."""
    return []


register("spend.month@1")(_project_scope)
register("spend.month_cancelled@1")(_project_scope)
register("spend.month_recorded@1")(_project_scope)
