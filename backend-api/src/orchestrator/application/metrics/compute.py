"""Every registered method over the same inputs."""

from __future__ import annotations

from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.values import MetricValue


def compute(inputs: RunInputs) -> list[MetricValue]:
    """The values of every registered method, in registry key order."""
    values: list[MetricValue] = []
    for key in sorted(REGISTRY):
        values += REGISTRY[key](inputs)
    return values
