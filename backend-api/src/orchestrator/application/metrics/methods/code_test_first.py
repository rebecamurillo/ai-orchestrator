"""`code.test_first_order@1`: which order each story's attempts wrote tests and production code in.

Read from the `event_fact` rows of the story's attempts, never from the diff. The outcome is a
fact about the method followed, not a score (SPEC CAP-3, decision P7).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from orchestrator.application.analysis.classify import classify
from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.summary import CENTS
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.stories import story_rows
from orchestrator.application.metrics.values import NO_STORY_FRAME, MetricValue, number, word
from orchestrator.application.rules.frames import story_frame
from orchestrator.domain.entities.facts import EventFact

METRIC = "code.test_first_order"
OUTCOMES = ("test_first", "test_with_code", "test_after", "not_readable")
TEST_CLASSES = ("test_unit", "test_e2e", "test_unclassified")


def _first(times: Sequence[datetime]) -> datetime | None:
    return min(times, default=None)


def outcome_of(events: Sequence[EventFact]) -> str:
    """The decision rule: total, and tried in this order."""
    tests: list[datetime] = []
    production: list[datetime] = []
    for event in events:
        if event.kind != "write" or event.path is None:
            continue
        file_class = classify(event.path, DEFAULT_DECLARATION, hub=False)
        if file_class in TEST_CLASSES:
            tests.append(event.at)
        elif file_class == "production":
            production.append(event.at)
    first_test, first_production = _first(tests), _first(production)
    if first_test is None and first_production is None:
        return "not_readable"
    if first_production is None:
        return "test_with_code"
    if first_test is None or first_production < first_test:
        return "test_after"
    failing = any(
        e.kind == "test_run" and e.exit_code not in (0, None) and e.at < first_production
        for e in events
    )
    if first_test < first_production and failing:
        return "test_first"
    return "test_with_code"


def _events_of(inputs: RunInputs, frame: str) -> list[EventFact]:
    return [
        event
        for attempt in inputs.attempts
        if story_frame(attempt.row.path) == frame and attempt.facts is not None
        for event in attempt.facts.events
    ]


@register(f"{METRIC}@1")
def first_order_values(inputs: RunInputs) -> list[MetricValue]:
    if not inputs.rows:
        return []
    frames = story_rows(inputs)
    if not frames:
        return [word(METRIC, "run", "run", NO_STORY_FRAME, unit="stories")]
    outcomes = {frame: outcome_of(_events_of(inputs, frame)) for frame in frames}
    values = [
        number(
            METRIC,
            "story",
            frame,
            1,
            source=outcome,
            scope_label=frames[frame][0].story_id,
            unit="story",
        )
        for frame, outcome in outcomes.items()
    ]
    held = list(outcomes.values())
    values += [
        number(METRIC, "run", "run", held.count(token), source=token, unit="stories")
        for token in OUTCOMES
    ]
    share = (Decimal(held.count("not_readable")) * 100 / len(held)).quantize(CENTS, ROUND_HALF_UP)
    values.append(number(METRIC, "run", "run", share, source="not_readable_share", unit="%"))
    readable = len(held) - held.count("not_readable")
    values += [
        number(METRIC, "run", "run", readable, source="readable", unit="stories"),
        number(METRIC, "run", "run", len(held), source="stories", unit="stories"),
    ]
    return values
