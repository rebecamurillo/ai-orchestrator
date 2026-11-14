"""Part A process methods: attempts, retries, failures, stories done, parks and gates."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.events import park_spans, retry_records
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import count_over_scopes
from orchestrator.application.metrics.stories import stories_done, story_rows
from orchestrator.application.metrics.values import MetricValue, na, number, word
from orchestrator.application.rules.frames import epic_frame, in_frame

COUNT = "count"
GATE_ROLES = ("verify", "spec-gate", "e2e")
FRAME_STEP = ("run", "epic", "story", "step")
FRAMES = ("run", "epic", "story")


@register("process.attempts@1")
def attempts(inputs: RunInputs) -> list[MetricValue]:
    items = [(a.row, a) for a in inputs.attempts]
    return count_over_scopes("process.attempts", inputs, (*FRAME_STEP, "role"), items)


@register("process.retries@1")
def retries(inputs: RunInputs) -> list[MetricValue]:
    rows = {r.path: r for r in inputs.rows}
    values: list[MetricValue] = []
    for kind, records in retry_records(inputs).items():
        items = [(rows[r.path], None) for r in records if r.path in rows]
        values += count_over_scopes("process.retries", inputs, FRAME_STEP, items, source=kind)
    return values


@register("process.failures@1")
def failures(inputs: RunInputs) -> list[MetricValue]:
    items = [(a.row, a) for a in inputs.attempts if a.attempt.status not in ("done", "skipped")]
    return count_over_scopes("process.failures", inputs, FRAME_STEP, items)


@register("process.stories_done@1")
def stories_done_method(inputs: RunInputs) -> list[MetricValue]:
    done, planned = stories_done(inputs)
    return [
        number("process.stories_done", "run", "run", done, source="done", unit=COUNT),
        number("process.stories_done", "run", "run", planned, source="planned", unit=COUNT),
    ]


@register("process.attempts_per_story@1")
def attempts_per_story(inputs: RunInputs) -> list[MetricValue]:
    frames = story_rows(inputs)
    if not frames:
        return [
            word(
                "process.attempts_per_story",
                "story",
                "",
                na("template has no story frame"),
                unit="ratio",
            )
        ]
    counts = {
        frame: sum(1 for a in inputs.attempts if in_frame(a.row.path, frame)) for frame in frames
    }
    labels = {frame: rows[0].story_id for frame, rows in frames.items()}
    values = [
        number(
            "process.attempts_per_story",
            "story",
            f,
            Decimal(c),
            scope_label=labels[f],
            unit="ratio",
        )
        for f, c in counts.items()
    ]
    groups = {"run": ("run", list(counts.values()))}
    for epic in {e for r in inputs.rows if (e := epic_frame(r.path)) is not None}:
        groups[epic] = ("epic", [c for f, c in counts.items() if in_frame(f, epic)])
    for key, (scope_type, found) in groups.items():
        if not found:
            continue
        stats = {"average": Decimal(sum(found)) / len(found), "maximum": Decimal(max(found))}
        values += [
            number("process.attempts_per_story", scope_type, key, v, source=k, unit="ratio")
            for k, v in stats.items()
        ]
    return values


@register("process.parks@1")
def parks(inputs: RunInputs) -> list[MetricValue]:
    spans = park_spans(inputs)
    values = [number("process.parks", "run", "run", len(spans), scope_label="run", unit=COUNT)]
    kinds = list(dict.fromkeys(s.kind for s in spans))
    values += [
        number(
            "process.parks",
            "run",
            "run",
            sum(1 for s in spans if s.kind == kind),
            scope_label=kind,
            source=kind,
            unit=COUNT,
        )
        for kind in kinds
    ]
    return values


@register("process.interventions@1")
def interventions(inputs: RunInputs) -> list[MetricValue]:
    count = sum(1 for r in inputs.records if r.actor == "operator")
    return [number("process.interventions", "run", "run", count, unit=COUNT)]


@register("process.gate_first_pass@1")
def gate_first_pass(inputs: RunInputs) -> list[MetricValue]:
    values: list[MetricValue] = []
    for row in inputs.rows:
        first = sorted(
            (a for a in inputs.attempts if a.row.path == row.path and a.attempt.role == "agent"),
            key=lambda a: a.attempt.n,
        )
        if row.role in GATE_ROLES and first:
            passed = 1 if first[0].attempt.status == "done" else 0
            values.append(
                number(
                    "process.gate_first_pass",
                    "gate",
                    row.path,
                    passed,
                    scope_label=row.label,
                    unit=COUNT,
                )
            )
    if not values:
        return [word("process.gate_first_pass", "run", "run", na("no gate step ran"), unit=COUNT)]
    total = sum((v.value_num or Decimal(0) for v in values), Decimal(0))
    return [number("process.gate_first_pass", "run", "run", total, unit=COUNT), *values]
