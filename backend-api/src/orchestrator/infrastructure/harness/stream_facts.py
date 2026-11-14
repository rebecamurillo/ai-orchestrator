"""What the Codex and OpenCode extractors share: framing, status and the usage row (AD-10)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import UsageClass, UsageFact
from orchestrator.domain.ports.log_facts import LogFactsCapabilities

NO_USAGE_EVENT = "no usage event"
UNKNOWN_EVENT_TYPES = "unknown event types: {types}"
#: The documented events of these two streams carry no timestamps, so none of the four can be read.
NO_CAPABILITIES = LogFactsCapabilities(
    per_request_usage=False, activity=False, events=False, harness_money_per_model=False
)


def split_events(
    objects: Iterable[dict[str, Any]], known: frozenset[str]
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """The objects that carry a string `type`, and the sorted distinct types not in `known`.

    An object without one is exporter noise, not an event, and is never reported as unknown.
    """
    events = [o for o in objects if isinstance(o.get("type"), str)]
    unknown = sorted({str(e["type"]) for e in events} - known)
    return events, tuple(unknown)


def status_and_reason(
    has_usage: bool, unknown: tuple[str, ...]
) -> tuple[Literal["ok", "partial"], str | None]:
    reasons = []
    if not has_usage:
        reasons.append(NO_USAGE_EVENT)
    if unknown:
        reasons.append(UNKNOWN_EVENT_TYPES.format(types=", ".join(unknown)))
    return ("partial", "; ".join(reasons)) if reasons else ("ok", None)


def usage_row(attempt: Attempt, usage_class: UsageClass, tokens: int) -> UsageFact:
    return UsageFact(
        source="harness",
        model=attempt.model,
        conversation="main",
        usage_class=usage_class,
        tokens=tokens,
    )
