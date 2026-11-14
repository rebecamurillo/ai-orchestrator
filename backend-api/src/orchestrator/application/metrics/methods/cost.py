"""Part A cost methods: the gateway and harness figures, apart, in every scope."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.events import RETRY_KINDS, created_attempts
from orchestrator.application.metrics.inputs import (
    AttemptInputs,
    RunInputs,
    gateway_usd,
    harness_rows,
    harness_usd,
)
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import Reading, sum_over_scopes
from orchestrator.application.metrics.stories import stories_done
from orchestrator.application.metrics.values import (
    NOT_AVAILABLE,
    NOT_RECORDED,
    MetricValue,
    na,
    number,
    word,
)

USD = "USD"
ALL = ("run", "epic", "story", "step", "attempt", "role", "model")
FRAMES = ("run", "epic", "story")
FIGURES = ("gateway", "harness")
UNFINISHED = ("done", "skipped")


def gateway_reading(ai: AttemptInputs) -> Reading:
    usd = gateway_usd(ai)
    if usd is not None:
        return usd
    return NOT_AVAILABLE if ai.reads else NOT_RECORDED


def harness_reading(ai: AttemptInputs) -> Reading:
    usd = harness_usd(ai)
    if usd is not None:
        return usd
    return NOT_AVAILABLE if ai.reads or ai.fact_set else NOT_RECORDED


def gateway_by_model(ai: AttemptInputs) -> dict[str, Decimal]:
    settled = next((usage for read, usage in ai.reads if not read.provisional), ())
    found: dict[str, Decimal] = {}
    for row in settled:
        if row.source == "gateway" and row.usage_class == "money" and row.usd is not None:
            name = row.model or ai.attempt.model or "unknown"
            found[name] = found.get(name, Decimal(0)) + row.usd
    return found


def harness_by_model(ai: AttemptInputs) -> dict[str, Decimal]:
    found: dict[str, Decimal] = {}
    for row in harness_rows(ai):
        name = row.model or ai.attempt.model or "unknown"
        found[name] = found.get(name, Decimal(0)) + (row.usd or Decimal(0))
    return found


READINGS = {
    "gateway": (gateway_reading, gateway_by_model),
    "harness": (harness_reading, harness_by_model),
}


@register("cost.gateway@1")
def gateway(inputs: RunInputs) -> list[MetricValue]:
    reading, by_model = READINGS["gateway"]
    return sum_over_scopes("cost.gateway", USD, inputs, ALL, reading, by_model=by_model)


@register("cost.harness@1")
def harness(inputs: RunInputs) -> list[MetricValue]:
    reading, by_model = READINGS["harness"]
    return sum_over_scopes("cost.harness", USD, inputs, ALL, reading, by_model=by_model)


def run_totals(inputs: RunInputs) -> dict[str, MetricValue]:
    return {
        "gateway": next(v for v in gateway(inputs) if v.scope_type == "run"),
        "harness": next(v for v in harness(inputs) if v.scope_type == "run"),
    }


@register("cost.figure_gap@1")
def figure_gap(inputs: RunInputs) -> list[MetricValue]:
    totals = run_totals(inputs)
    gateway, harness = totals["gateway"], totals["harness"]
    if gateway.missing or harness.missing or gateway.value_num is None or harness.value_num is None:
        return [word("cost.figure_gap", "run", "run", NOT_AVAILABLE, unit=USD)]
    gap = abs(gateway.value_num - harness.value_num).quantize(Decimal("0.01"))
    return [number("cost.figure_gap", "run", "run", gap, unit=USD)]


def _created(
    inputs: RunInputs, metric_id: str, subset: dict[str, list[AttemptInputs]]
) -> list[MetricValue]:
    values: list[MetricValue] = []
    union = [a for kind in RETRY_KINDS for a in subset[kind]]
    union = list({id(a): a for a in union}.values())
    for figure in FIGURES:
        reading = READINGS[figure][0]
        selections = {figure: union, **{f"{figure}:{kind}": subset[kind] for kind in RETRY_KINDS}}
        for source, attempts in selections.items():
            values += sum_over_scopes(
                metric_id, USD, inputs, FRAMES, reading, source=source, attempts=attempts
            )
    return values


@register("cost.retries@1")
def retries(inputs: RunInputs) -> list[MetricValue]:
    return _created(inputs, "cost.retries", created_attempts(inputs))


@register("cost.failures@1")
def failures(inputs: RunInputs) -> list[MetricValue]:
    failed = [a for a in inputs.attempts if a.attempt.status not in UNFINISHED]
    values: list[MetricValue] = []
    for figure in FIGURES:
        values += sum_over_scopes(
            "cost.failures",
            USD,
            inputs,
            FRAMES,
            READINGS[figure][0],
            source=figure,
            attempts=failed,
        )
    return values


@register("cost.per_story_done@1")
def per_story_done(inputs: RunInputs) -> list[MetricValue]:
    done, _ = stories_done(inputs)
    totals = run_totals(inputs)
    values: list[MetricValue] = []
    for figure, total in totals.items():
        if done == 0:
            values.append(
                word(
                    "cost.per_story_done",
                    "run",
                    "run",
                    na("no story done"),
                    source=figure,
                    unit=USD,
                )
            )
        elif total.value_num is None:
            values.append(
                word(
                    "cost.per_story_done",
                    "run",
                    "run",
                    total.missing or NOT_RECORDED,
                    source=figure,
                    unit=USD,
                )
            )
        else:
            values.append(
                MetricValue(
                    "cost.per_story_done",
                    "cost.per_story_done@1",
                    "run",
                    "run",
                    source=figure,
                    value_num=total.value_num / done,
                    unit=USD,
                    missing=total.missing,
                    partial_n=total.partial_n,
                    partial_m=total.partial_m,
                )
            )
    return values
