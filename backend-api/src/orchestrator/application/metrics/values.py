"""The value one metric method produces, and the words that stand in for a missing figure.

A value never carries 0 in place of a figure that is missing: `value_num` is `None` and
`missing` says why, in the words below.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

NOT_RECORDED = "not recorded"
NOT_AVAILABLE = "not available"
PARTIAL = "partial"
NO_SUCH_STEP = "no such step in this template"
NO_STORY_FRAME = "n/a — template has no story frame"
NO_MODEL_CALLED = "n/a — shell step, no model called"


def na(reason: str) -> str:
    return f"n/a — {reason}"


@dataclass(frozen=True)
class MetricValue:
    metric_id: str
    method_id: str
    scope_type: str
    scope_key: str
    scope_label: str | None = None
    role: str | None = None
    model: str | None = None
    repository: str | None = None
    attempt_n: int | None = None
    source: str | None = None
    value_num: Decimal | None = None
    unit: str = ""
    missing: str | None = None
    partial_n: int | None = None
    partial_m: int | None = None
    carried_from: int | None = None


def number(
    metric_id: str, scope_type: str, scope_key: str, value: Decimal | int, **fields: object
) -> MetricValue:
    """A value holding a figure; `method_id` is `{metric_id}@1`."""
    return MetricValue(
        metric_id,
        f"{metric_id}@1",
        scope_type,
        scope_key,
        value_num=Decimal(value),
        **fields,  # type: ignore[arg-type]
    )


def word(
    metric_id: str, scope_type: str, scope_key: str, missing: str, **fields: object
) -> MetricValue:
    """A value holding no figure, only the word that says why."""
    return MetricValue(
        metric_id,
        f"{metric_id}@1",
        scope_type,
        scope_key,
        missing=missing,
        **fields,  # type: ignore[arg-type]
    )


def value_at(
    values: list[MetricValue],
    metric_id: str,
    scope_type: str,
    scope_key: str,
    source: str | None = None,
) -> MetricValue:
    """The value at that scope, or one reading `no such step in this template`."""
    for value in values:
        if (value.metric_id, value.scope_type, value.scope_key, value.source) == (
            metric_id,
            scope_type,
            scope_key,
            source,
        ):
            return value
    return word(metric_id, scope_type, scope_key, NO_SUCH_STEP, source=source)
