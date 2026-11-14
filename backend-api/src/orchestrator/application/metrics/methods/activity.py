"""Part A activity methods: what the conversations did, from the chosen fact set."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.methods import register
from orchestrator.application.metrics.scopes import (
    Agg,
    Measure,
    Reading,
    Scope,
    scopes_of,
    sum_over_scopes,
    to_value,
)
from orchestrator.application.metrics.values import NOT_AVAILABLE, NOT_RECORDED, MetricValue
from orchestrator.domain.entities.facts import AttemptFacts

MIN_GAP_SECONDS = 60
SESSION_CACHE_SECONDS = 3600
SUBAGENT_CACHE_SECONDS = 300
MAIN = "main"
COUNT = "count"
SECONDS = "seconds"
MESSAGE_SCOPES = ("run", "epic", "story", "attempt")
RUN_ATTEMPT = ("run", "attempt")


def _facts(ai: AttemptInputs) -> AttemptFacts | str:
    return NOT_RECORDED if ai.facts is None else ai.facts


def _from_facts(pick: Callable[[AttemptFacts], Decimal | None]) -> Measure:
    def read(ai: AttemptInputs) -> Reading:
        facts = _facts(ai)
        if isinstance(facts, str):
            return facts
        found = pick(facts)
        return NOT_AVAILABLE if found is None else found

    return read


def _messages(main: bool) -> Measure:
    def pick(facts: AttemptFacts) -> Decimal | None:
        ours = [g.messages for g in facts.gaps if (g.conversation == MAIN) is main]
        return Decimal(sum(ours)) if ours else None

    return _from_facts(pick)


@register("activity.messages_session@1")
def messages_session(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "activity.messages_session",
        COUNT,
        inputs,
        MESSAGE_SCOPES,
        _messages(True),
        model_only=False,
    )


@register("activity.messages_subagents@1")
def messages_subagents(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "activity.messages_subagents",
        COUNT,
        inputs,
        MESSAGE_SCOPES,
        _messages(False),
        model_only=False,
    )


def _over_cache(facts: AttemptFacts) -> Decimal | None:
    if not facts.gaps:
        return None
    limit = {True: SESSION_CACHE_SECONDS, False: SUBAGENT_CACHE_SECONDS}
    return Decimal(
        sum(1 for g in facts.gaps for s in g.gaps_s if s > limit[g.conversation == MAIN])
    )


@register("activity.pauses_over_cache_lifetime@1")
def pauses_over_cache_lifetime(inputs: RunInputs) -> list[MetricValue]:
    return sum_over_scopes(
        "activity.pauses_over_cache_lifetime",
        COUNT,
        inputs,
        MESSAGE_SCOPES,
        _from_facts(_over_cache),
        model_only=False,
    )


def _longest(facts: AttemptFacts, conversation: str | None = None) -> Decimal | None:
    gaps = [g for g in facts.gaps if conversation in (None, g.conversation)]
    if not gaps:
        return None
    return Decimal(max((s for g in gaps for s in g.gaps_s if s >= MIN_GAP_SECONDS), default=0))


@register("activity.pause_longest@1")
def pause_longest(inputs: RunInputs) -> list[MetricValue]:
    """The largest gap, kept as a maximum — never summed — in every scope."""
    maxima: dict[Scope, Agg] = {}

    def keep(scope: Scope, reading: Reading) -> None:
        agg = maxima.setdefault(scope, Agg(scope))
        agg.m += 1
        if isinstance(reading, Decimal):
            agg.total = reading if agg.n == 0 else max(agg.total, reading)
            agg.n += 1
        else:
            agg.words = [*(agg.words or []), reading]

    for ai in inputs.attempts:
        facts = _facts(ai)
        if isinstance(facts, str):
            for scope in scopes_of(inputs, ai, RUN_ATTEMPT):
                keep(scope, facts)
            continue
        for scope in scopes_of(inputs, ai, RUN_ATTEMPT):
            found = _longest(facts)
            keep(scope, NOT_AVAILABLE if found is None else found)
        for name in dict.fromkeys(g.conversation for g in facts.gaps):
            keep(Scope("conversation", name, name), _longest(facts, name) or Decimal(0))
    return [to_value("activity.pause_longest", SECONDS, agg) for agg in maxima.values()]


def _tool_total(field: str) -> Measure:
    return _from_facts(
        lambda f: Decimal(sum(getattr(a, field) for a in f.activity)) if f.activity else None
    )


def _tool_values(metric_id: str, field: str, inputs: RunInputs) -> list[MetricValue]:
    values = sum_over_scopes(
        metric_id, COUNT, inputs, RUN_ATTEMPT, _tool_total(field), model_only=False
    )
    totals: dict[str, int] = {}
    for ai in inputs.attempts:
        if ai.facts is not None:
            for fact in ai.facts.activity:
                totals[fact.tool] = totals.get(fact.tool, 0) + getattr(fact, field)
    return values + [
        to_value(metric_id, COUNT, Agg(Scope("tool", tool, tool), Decimal(n), 1, 1))
        for tool, n in totals.items()
    ]


@register("activity.tool_calls@1")
def tool_calls(inputs: RunInputs) -> list[MetricValue]:
    return _tool_values("activity.tool_calls", "calls", inputs)


@register("activity.tool_errors@1")
def tool_errors(inputs: RunInputs) -> list[MetricValue]:
    return _tool_values("activity.tool_errors", "errors", inputs)


def _plain(metric_id: str, field: str) -> Callable[[RunInputs], list[MetricValue]]:
    def method(inputs: RunInputs) -> list[MetricValue]:
        return sum_over_scopes(
            metric_id, COUNT, inputs, RUN_ATTEMPT, _tool_total(field), model_only=False
        )

    return method


register("activity.files_read@1")(_plain("activity.files_read", "files_read"))
register("activity.files_edited@1")(_plain("activity.files_edited", "files_edited"))
register("activity.test_runs@1")(_plain("activity.test_runs", "test_runs"))
