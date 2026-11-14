"""Scope keys (ARCHITECTURE §5.6) and the one aggregator that applies the missing rules.

A per-attempt reading is a `Decimal` or a missing word. Over the model-calling attempts of a
scope (`m`), those holding a figure (`n`): all → the sum; some → the sum with `partial`, `n`
and `m`; none → the word. Nothing here turns a missing figure into 0.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import TypedDict, Unpack

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.values import (
    NO_MODEL_CALLED,
    NO_STORY_FRAME,
    NOT_AVAILABLE,
    NOT_RECORDED,
    PARTIAL,
    MetricValue,
)
from orchestrator.application.rules.frames import epic_frame, story_frame
from orchestrator.domain.entities.step_run import StepRun

Reading = Decimal | str
Measure = Callable[[AttemptInputs], Reading]
ByModel = Callable[[AttemptInputs], dict[str, Decimal]]

ROOT_REPOSITORY = "."


@dataclass(frozen=True)
class Scope:
    scope_type: str
    key: str
    label: str | None = None
    role: str | None = None
    model: str | None = None
    repository: str | None = None
    attempt_n: int | None = None


def can_call_model(ai: AttemptInputs) -> bool:
    return ai.row.kind == "agent" or ai.attempt.role in ("consult", "session")


def repository_of(row: StepRun, known: Iterable[str]) -> str:
    workdir = row.with_resolved.get("workdir")
    return workdir if isinstance(workdir, str) and workdir in set(known) else ROOT_REPOSITORY


def run_scope() -> Scope:
    return Scope("run", "run", "run")


def frame_scopes(row: StepRun) -> list[Scope]:
    found: list[Scope] = []
    if (epic := epic_frame(row.path)) is not None:
        found.append(Scope("epic", epic, epic))
    if (story := story_frame(row.path)) is not None:
        found.append(Scope("story", story, row.story_id))
    return found


def attempt_key(ai: AttemptInputs) -> str:
    return f"{ai.row.path}#{ai.attempt.n}"


def scopes_of(inputs: RunInputs, ai: AttemptInputs, types: Iterable[str]) -> list[Scope]:
    """Every scope of the requested types, other than `model`, this attempt belongs to."""
    wanted = set(types)
    repo = repository_of(ai.row, (r.path for r in inputs.run_repositories))
    found = [run_scope(), *frame_scopes(ai.row)]
    found.append(Scope("step", ai.row.path, ai.row.label, repository=repo))
    found.append(
        Scope(
            "attempt",
            attempt_key(ai),
            ai.row.label,
            role=ai.role,
            model=ai.attempt.model,
            repository=repo,
            attempt_n=ai.attempt.n,
        )
    )
    found.append(Scope("role", ai.role, ai.role, role=ai.role))
    return [s for s in found if s.scope_type in wanted]


@dataclass
class Agg:
    scope: Scope
    total: Decimal = Decimal(0)
    n: int = 0
    m: int = 0
    words: list[str] | None = None

    def add(self, reading: Reading) -> None:
        self.m += 1
        if isinstance(reading, Decimal):
            self.n += 1
            self.total += reading
        else:
            self.words = [*(self.words or []), reading]

    @property
    def word(self) -> str:
        words = set(self.words or [])
        return words.pop() if len(words) == 1 else NOT_AVAILABLE


class Options(TypedDict, total=False):
    by_model: ByModel
    source: str
    model_only: bool
    attempts: Sequence[AttemptInputs]


def aggregate(
    inputs: RunInputs, types: Sequence[str], measure: Measure, **options: Unpack[Options]
) -> dict[Scope, Agg]:
    """Per-scope sums of `measure`, with the counts the missing rules need."""
    groups: dict[Scope, Agg] = {}
    by_model = options.get("by_model")
    model_only = options.get("model_only", True)

    def put(scope: Scope, reading: Reading) -> None:
        groups.setdefault(scope, Agg(scope)).add(reading)

    for ai in options.get("attempts", inputs.attempts):
        if model_only and not can_call_model(ai):
            # Attempt scope only: on the step, a session attempt on a shell row must not be
            # read as one of two; a row with no model-calling attempt gets its word below.
            for scope in scopes_of(inputs, ai, [t for t in ("attempt",) if t in types]):
                put(scope, NO_MODEL_CALLED)
            continue
        reading = measure(ai)
        models = by_model(ai) if by_model and isinstance(reading, Decimal) else {}
        if "model" in types and models:
            for name, amount in models.items():
                put(Scope("model", name, name, model=name), amount)
        elif "model" in types:
            name = ai.attempt.model or "unknown"
            put(Scope("model", name, name, model=name), reading)
        for scope in scopes_of(inputs, ai, [t for t in types if t != "model"]):
            put(scope, reading)
    return groups


def to_value(metric_id: str, unit: str, agg: Agg, source: str | None = None) -> MetricValue:
    scope = agg.scope
    common = {
        "metric_id": metric_id,
        "method_id": f"{metric_id}@1",
        "scope_type": scope.scope_type,
        "scope_key": scope.key,
        "scope_label": scope.label,
        "role": scope.role,
        "model": scope.model,
        "repository": scope.repository,
        "attempt_n": scope.attempt_n,
        "source": source,
        "unit": unit,
    }
    if agg.n == 0:
        return MetricValue(**common, missing=agg.word)  # type: ignore[arg-type]
    if agg.n < agg.m:
        return MetricValue(
            **common,  # type: ignore[arg-type]
            value_num=agg.total,
            missing=PARTIAL,
            partial_n=agg.n,
            partial_m=agg.m,
        )
    return MetricValue(**common, value_num=agg.total)  # type: ignore[arg-type]


def no_story_frame(
    metric_id: str, unit: str, inputs: RunInputs, types: Sequence[str], source: str | None = None
) -> list[MetricValue]:
    """One `story` value reading `n/a — template has no story frame`, when the plan has none."""
    if "story" not in types or any(story_frame(r.path) for r in inputs.rows):
        return []
    return [
        MetricValue(
            metric_id,
            f"{metric_id}@1",
            "story",
            "",
            missing=NO_STORY_FRAME,
            source=source,
            unit=unit,
        )
    ]


def empty_scope_values(
    make: Callable[..., MetricValue],
    inputs: RunInputs,
    types: Sequence[str],
    groups: dict[Scope, Agg],
    subset: bool,
) -> list[MetricValue]:
    """Rows that no attempt reached still get their word: run scope and shell step rows.

    Over a subset of the attempts, none selected is a real zero, not a missing figure.
    """
    values: list[MetricValue] = []
    if run_scope() not in groups and "run" in types:
        if subset:
            values.append(make("run", "run", "run", value_num=Decimal(0)))
        else:
            word = NO_MODEL_CALLED if all(r.kind != "agent" for r in inputs.rows) else NOT_RECORDED
            values.append(make("run", "run", "run", missing=word))
    if "step" in types and not subset:
        seen = {s.key for s in groups if s.scope_type == "step"}
        for row in inputs.rows:
            if row.path not in seen and row.kind != "agent":
                repo = repository_of(row, (r.path for r in inputs.run_repositories))
                values.append(
                    make("step", row.path, row.label, repository=repo, missing=NO_MODEL_CALLED)
                )
    return values


def sum_over_scopes(
    metric_id: str,
    unit: str,
    inputs: RunInputs,
    types: Sequence[str],
    measure: Measure,
    **options: Unpack[Options],
) -> list[MetricValue]:
    """The sum of `measure` in every requested scope, missing figures said in words."""
    source = options.get("source")
    groups = aggregate(inputs, types, measure, **options)
    make = partial(MetricValue, metric_id, f"{metric_id}@1", unit=unit, source=source)
    values = [to_value(metric_id, unit, agg, source) for agg in groups.values()]
    values += empty_scope_values(make, inputs, types, groups, "attempts" in options)
    return values + no_story_frame(metric_id, unit, inputs, types, source)


def row_scopes(inputs: RunInputs, row: StepRun, types: Iterable[str]) -> list[Scope]:
    """The scopes of a row that has no attempt behind it: run, epic, story and step."""
    wanted = set(types)
    repo = repository_of(row, (r.path for r in inputs.run_repositories))
    found = [run_scope(), *frame_scopes(row), Scope("step", row.path, row.label, repository=repo)]
    return [s for s in found if s.scope_type in wanted]


def count_over_scopes(
    metric_id: str,
    inputs: RunInputs,
    types: Sequence[str],
    items: Iterable[tuple[StepRun, AttemptInputs | None]],
    source: str | None = None,
) -> list[MetricValue]:
    """One count per scope; the run always has one, so zero is said as 0, other scopes only
    when something was counted."""
    counts: dict[Scope, int] = {run_scope(): 0}
    for row, ai in items:
        found = scopes_of(inputs, ai, types) if ai is not None else row_scopes(inputs, row, types)
        for scope in found:
            counts[scope] = counts.get(scope, 0) + 1
    values = [
        MetricValue(
            metric_id,
            f"{metric_id}@1",
            scope.scope_type,
            scope.key,
            scope.label,
            scope.role,
            scope.model,
            scope.repository,
            scope.attempt_n,
            source,
            Decimal(count),
            "count",
        )
        for scope, count in counts.items()
        if "run" in types or scope.scope_type != "run"
    ]
    return values + no_story_frame(metric_id, "count", inputs, types, source)
