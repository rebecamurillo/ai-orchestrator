"""Values of the step-produced metrics a Run's template catalogued (epic 6 story 3).

Not registered methods: a step id is declared per template version, not shipped, so the rows
come from the Run's own repository's signals and carry the method id `{metric_id}@1`.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.summary import CENTS
from orchestrator.application.metrics.values import MetricValue, na, number, word
from orchestrator.domain.entities.run_records import ROOT_PATH

STEP_PREFIX = "step."
LINE_SOURCES = ("covered", "instrumented")
SHARE = "share"
NO_INSTRUMENTED = na("no line instrumented")


def _root(code: Sequence[RepositorySignals]) -> RepositorySignals | None:
    return next((s for s in code if s.path == ROOT_PATH), None)


def _share(metric_id: str, covered: int, instrumented: int) -> MetricValue:
    fields = {"source": SHARE, "repository": ROOT_PATH}
    if instrumented == 0:
        return word(metric_id, "run", "run", NO_INSTRUMENTED, **fields)
    figure = (Decimal(covered) * 100 / instrumented).quantize(CENTS, ROUND_HALF_UP)
    return number(metric_id, "run", "run", figure, unit="%", **fields)


def step_values(code: Sequence[RepositorySignals]) -> list[MetricValue]:
    """Counts, coverage shares and words of the declared step ids, from the Run's repository."""
    signals = _root(code)
    if signals is None:
        return []
    values: list[MetricValue] = []
    held: dict[str, dict[str, int]] = {}
    for count in signals.counts:
        if not count.metric_id.startswith(STEP_PREFIX) or count.source is None:
            continue
        held.setdefault(count.metric_id, {})[count.source] = count.value
        unit = "lines" if count.source in LINE_SOURCES else "count"
        values.append(
            number(
                count.metric_id,
                "run",
                "run",
                count.value,
                source=count.source,
                repository=ROOT_PATH,
                unit=unit,
            )
        )
    values += [
        _share(metric_id, sources["covered"], sources["instrumented"])
        for metric_id, sources in held.items()
        if "covered" in sources
    ]
    values += [
        word(metric_id, "run", "run", missing, repository=ROOT_PATH)
        for metric_id, missing in signals.words.items()
        if metric_id.startswith(STEP_PREFIX)
    ]
    return values


def not_catalogued(code: Sequence[RepositorySignals]) -> tuple[str, ...]:
    signals = _root(code)
    return () if signals is None else signals.not_catalogued
