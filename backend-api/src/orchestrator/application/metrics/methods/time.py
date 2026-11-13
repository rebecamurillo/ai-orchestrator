"""Part A time methods: wall-clock, waiting on you, machine time and attempt time."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from statistics import median

from orchestrator.application.metrics.events import (
    ParkSpan,
    created_attempts,
    duration,
    park_spans,
)
from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import (
    Reading,
    Scope,
    frame_scopes,
    no_story_frame,
    sum_over_scopes,
)
from orchestrator.application.metrics.values import (
    NOT_RECORDED,
    MetricValue,
    na,
    number,
    word,
)
from orchestrator.application.rules.frames import in_frame

SECONDS = "seconds"
FRAMES = ("run", "epic", "story")


def _seconds(start: datetime, end: datetime) -> Decimal:
    return Decimal(int((end - start).total_seconds()))


def run_wall(inputs: RunInputs) -> Decimal | None:
    started = inputs.run.started_at
    if started is None:
        return None
    return _seconds(started, inputs.run.ended_at or inputs.now)


def _frame_window(inputs: RunInputs, frame: str) -> tuple[datetime, datetime] | None:
    """First attempt start to last attempt end; an attempt left open ends with the Run."""
    ours = [a.attempt for a in inputs.attempts if in_frame(a.row.path, frame)]
    starts = [a.started_at for a in ours if a.started_at is not None]
    if not starts:
        return None
    ends = [a.ended_at or inputs.run.ended_at or inputs.now for a in ours]
    return min(starts), max(ends)


def _frame_wall(inputs: RunInputs, frame: str) -> Decimal | None:
    window = _frame_window(inputs, frame)
    return None if window is None else _seconds(*window)


def frame_walls(inputs: RunInputs) -> dict[Scope, Decimal]:
    found: dict[Scope, Decimal] = {}
    for row in inputs.rows:
        for scope in frame_scopes(row):
            if scope not in found and (wall := _frame_wall(inputs, scope.key)) is not None:
                found[scope] = wall
    return found


def _wall_values(inputs: RunInputs, metric_id: str) -> list[MetricValue]:
    run = run_wall(inputs)
    values = [
        word(metric_id, "run", "run", NOT_RECORDED, scope_label="run", unit=SECONDS)
        if run is None
        else number(metric_id, "run", "run", run, scope_label="run", unit=SECONDS)
    ]
    for scope, wall in frame_walls(inputs).items():
        values.append(
            number(
                metric_id, scope.scope_type, scope.key, wall, scope_label=scope.label, unit=SECONDS
            )
        )
    return values + no_story_frame(metric_id, SECONDS, inputs, FRAMES)


@register("time.wall@1")
def wall(inputs: RunInputs) -> list[MetricValue]:
    return _wall_values(inputs, "time.wall")


def _parked_in(spans: Sequence[ParkSpan], frame: str | None) -> Decimal:
    return sum(
        (s.seconds for s in spans if frame is None or (s.path and in_frame(s.path, frame))),
        Decimal(0),
    )


def _parked_within(inputs: RunInputs, spans: Sequence[ParkSpan], frame: str) -> Decimal:
    """Parks on the frame's rows, clipped to its wall window: a park after the frame's last
    attempt (a checkpoint closing a story) is not inside that wall and must not shrink it."""
    window = _frame_window(inputs, frame)
    assert window is not None
    total = Decimal(0)
    for span in spans:
        if span.path and in_frame(span.path, frame):
            start, end = max(span.start, window[0]), min(span.end, window[1])
            if end > start:
                total += _seconds(start, end)
    return total


@register("time.parked@1")
def parked(inputs: RunInputs) -> list[MetricValue]:
    spans = park_spans(inputs)
    values = [
        number(
            "time.parked", "run", "run", _parked_in(spans, None), scope_label="run", unit=SECONDS
        )
    ]
    values += [
        number("time.parked", "park", str(s.position), s.seconds, scope_label=s.kind, unit=SECONDS)
        for s in spans
    ]
    return values


@register("time.machine@1")
def machine(inputs: RunInputs) -> list[MetricValue]:
    spans = park_spans(inputs)
    values: list[MetricValue] = []
    for value in _wall_values(inputs, "time.machine"):
        if value.value_num is None:
            values.append(value)
            continue
        parked = (
            _parked_in(spans, None)
            if value.scope_type == "run"
            else _parked_within(inputs, spans, value.scope_key)
        )
        values.append(
            number(
                "time.machine",
                value.scope_type,
                value.scope_key,
                value.value_num - parked,
                scope_label=value.scope_label,
                unit=SECONDS,
            )
        )
    return values


def duration_reading(ai: AttemptInputs) -> Reading:
    found = duration(ai)
    return NOT_RECORDED if found is None else found


@register("time.attempt_seconds@1")
def attempt_seconds(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "time.attempt_seconds",
        SECONDS,
        inputs,
        ("run", "role", "model"),
        duration_reading,
        model_only=False,
    )


@register("time.by_role@1")
def by_role(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "time.by_role", SECONDS, inputs, ("run", "role"), duration_reading, model_only=False
    )


@register("time.operator_active@1")
def operator_active(inputs: RunInputs) -> list[MetricValue]:
    return [number("time.operator_active", "run", "run", inputs.run.active_seconds, unit=SECONDS)]


def _stats(metric_id: str, scope: Scope, walls: list[Decimal], empty: str) -> list[MetricValue]:
    if not walls:
        return [word(metric_id, scope.scope_type, scope.key, empty, unit=SECONDS)]
    found = {
        "average": sum(walls, Decimal(0)) / len(walls),
        "median": Decimal(median(walls)),
        "longest": max(walls),
    }
    return [
        number(
            metric_id,
            scope.scope_type,
            scope.key,
            v,
            scope_label=scope.label,
            source=k,
            unit=SECONDS,
        )
        for k, v in found.items()
    ]


@register("time.story_wall_stats@1")
def story_wall_stats(inputs: RunInputs) -> list[MetricValue]:
    walls = frame_walls(inputs)
    stories = {s: w for s, w in walls.items() if s.scope_type == "story"}
    no_frame = na("template has no story frame")
    values = _stats(
        "time.story_wall_stats", Scope("run", "run", "run"), list(stories.values()), no_frame
    )
    for epic in (s for s in walls if s.scope_type == "epic"):
        ours = [w for s, w in stories.items() if in_frame(s.key, epic.key)]
        values += _stats("time.story_wall_stats", epic, ours, no_frame)
    return values


@register("time.epic_wall_stats@1")
def epic_wall_stats(inputs: RunInputs) -> list[MetricValue]:
    walls = [w for s, w in frame_walls(inputs).items() if s.scope_type == "epic"]
    return _stats(
        "time.epic_wall_stats", Scope("run", "run", "run"), walls, na("template has no epic frame")
    )


@register("time.retries@1")
def retries(inputs: RunInputs) -> list[MetricValue]:
    created = created_attempts(inputs)
    union = list({id(a): a for kind in created.values() for a in kind}.values())
    return sum_over_scopes(
        "time.retries", SECONDS, inputs, FRAMES, duration_reading, attempts=union, model_only=False
    )


@register("time.failures@1")
def failures(inputs: RunInputs) -> list[MetricValue]:
    failed = [a for a in inputs.attempts if a.attempt.status not in ("done", "skipped")]
    return sum_over_scopes(
        "time.failures",
        SECONDS,
        inputs,
        FRAMES,
        duration_reading,
        attempts=failed,
        model_only=False,
    )
