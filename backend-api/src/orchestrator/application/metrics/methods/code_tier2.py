"""Part C Tier 2 methods: the rows of the repository's own commands at base and head.

Kept apart from `code.py` so `CODE_IDS` stays the Tier 1 ids; each answers from the same summary
of the repositories' signals.
"""

from __future__ import annotations

from orchestrator.application.analysis.summary import summarise
from orchestrator.application.analysis.tier2 import TIER2_IDS
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import Method, register
from orchestrator.application.metrics.values import MetricValue


def _method(metric_id: str) -> Method:
    def compute(inputs: RunInputs) -> list[MetricValue]:
        return [v for v in summarise(inputs.code) if v.metric_id == metric_id]

    return compute


for _id in TIER2_IDS:
    register(f"{_id}@1")(_method(_id))
