"""Part A token methods: harness usage rows of the chosen fact set (D17), gateway reads apart."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import (
    Agg,
    ByModel,
    Measure,
    Reading,
    aggregate,
    sum_over_scopes,
    to_value,
)
from orchestrator.application.metrics.values import (
    NOT_AVAILABLE,
    NOT_RECORDED,
    MetricValue,
)
from orchestrator.domain.entities.facts import UsageFact

TOKENS = "tokens"
ALL = ("run", "epic", "story", "step", "attempt", "role", "model")
GATEWAY = ("run", "epic", "story", "step", "attempt")
RECORDED = ("run", "epic", "story", "step", "attempt")
SHARE = ("run", "epic", "story", "role")
INPUT = ("input_uncached",)
CACHE_WRITE = ("cache_write_5m", "cache_write_1h", "cache_write_unsplit")


def _rows(ai: AttemptInputs, classes: tuple[str, ...]) -> list[UsageFact]:
    assert ai.facts is not None
    return [
        u
        for u in ai.facts.usage
        if u.source == "harness" and u.usage_class in classes and u.tokens is not None
    ]


def class_reading(classes: tuple[str, ...]) -> Measure:
    def read(ai: AttemptInputs) -> Reading:
        if ai.facts is None:
            return NOT_RECORDED
        rows = _rows(ai, classes)
        return Decimal(sum(u.tokens or 0 for u in rows)) if rows else NOT_AVAILABLE

    return read


def class_by_model(classes: tuple[str, ...]) -> ByModel:
    def split(ai: AttemptInputs) -> dict[str, Decimal]:
        found: dict[str, Decimal] = {}
        for row in _rows(ai, classes):
            name = row.model or ai.attempt.model or "unknown"
            found[name] = found.get(name, Decimal(0)) + Decimal(row.tokens or 0)
        return found

    return split


def _harness_class(
    metric_id: str, classes: tuple[str, ...]
) -> Callable[[RunInputs], list[MetricValue]]:
    def method(inputs: RunInputs) -> list[MetricValue]:
        return sum_over_scopes(
            metric_id,
            TOKENS,
            inputs,
            ALL,
            class_reading(classes),
            by_model=class_by_model(classes),
        )

    return method


for _name, _classes in (
    ("input", INPUT),
    ("output", ("output",)),
    ("cache_read", ("cache_read",)),
    ("cache_write", CACHE_WRITE),
    ("cache_write_5m", ("cache_write_5m",)),
    ("cache_write_1h", ("cache_write_1h",)),
    ("thinking", ("thinking",)),
):
    register(f"tokens.{_name}@1")(_harness_class(f"tokens.{_name}", _classes))


def _gateway_reading(usage_class: str, fallback: str) -> Measure:
    def read(ai: AttemptInputs) -> Reading:
        if not ai.reads:
            return NOT_RECORDED
        read, usage = next(((r, u) for r, u in ai.reads if not r.provisional), ai.reads[0])
        rows = [u for u in usage if u.source == "gateway" and u.usage_class == usage_class]
        if rows and all(u.tokens is not None for u in rows):
            return Decimal(sum(u.tokens or 0 for u in rows))
        fallback_value = getattr(read, fallback)
        return NOT_AVAILABLE if fallback_value is None else Decimal(fallback_value)

    return read


@register("tokens.gateway_prompt@1")
def gateway_prompt(inputs: RunInputs) -> list[MetricValue]:
    measure = _gateway_reading("gateway_prompt", "prompt")
    return sum_over_scopes("tokens.gateway_prompt", TOKENS, inputs, GATEWAY, measure)


@register("tokens.gateway_completion@1")
def gateway_completion(inputs: RunInputs) -> list[MetricValue]:
    measure = _gateway_reading("gateway_completion", "completion")
    return sum_over_scopes("tokens.gateway_completion", TOKENS, inputs, GATEWAY, measure)


def _recorded(attr: str) -> Measure:
    def read(ai: AttemptInputs) -> Reading:
        value = getattr(ai.attempt, attr)
        return NOT_RECORDED if value is None else Decimal(value)

    return read


@register("tokens.recorded_in@1")
def recorded_in(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "tokens.recorded_in", TOKENS, inputs, RECORDED, _recorded("tokens_in"), model_only=False
    )


@register("tokens.recorded_out@1")
def recorded_out(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "tokens.recorded_out", TOKENS, inputs, RECORDED, _recorded("tokens_out"), model_only=False
    )


@register("tokens.cache_hit_share@1")
def cache_hit_share(inputs: RunInputs) -> list[MetricValue]:
    """Cache read ÷ (cache read + cache write + uncached input), from the summed classes."""
    reads = aggregate(inputs, SHARE, class_reading(("cache_read",)))
    writes = aggregate(inputs, SHARE, class_reading(CACHE_WRITE))
    fresh = aggregate(inputs, SHARE, class_reading(INPUT))
    values: list[MetricValue] = []
    for scope, read in reads.items():
        parts = (read, writes[scope], fresh[scope])
        denominator = sum((p.total for p in parts), Decimal(0))
        if any(p.n < p.m for p in parts) or denominator == 0:
            words = [w for p in parts for w in (p.words or [])]
            word = (
                NOT_RECORDED if words and all(w == NOT_RECORDED for w in words) else NOT_AVAILABLE
            )
            values.append(
                to_value("tokens.cache_hit_share", "ratio", Agg(scope, m=1, words=[word]))
            )
        else:
            ratio = Agg(scope, read.total / denominator, 1, 1)
            values.append(to_value("tokens.cache_hit_share", "ratio", ratio))
    return values
