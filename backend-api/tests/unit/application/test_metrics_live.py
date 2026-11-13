"""`load_inputs`, `compute`, `stories` and `events` (epic 2 story 4)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from orchestrator.application.metrics.compute import compute
from orchestrator.application.metrics.events import created_attempts, park_spans, retry_records
from orchestrator.application.metrics.live import live_values, load_inputs
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.stories import stories_done, story_rows
from orchestrator.domain.entities.facts import AttemptFacts, FactSet
from tests.unit.application.metrics_builders import (
    at,
    make_ai,
    make_attempt,
    make_inputs,
    make_record,
    make_row,
    make_run,
)
from tests.unit.application.metrics_fixed_run import RUN_ID, build_fixed_run

ATTEMPTS = 12
OPEN_FOR = 1000


def test_load_inputs_picks_one_fact_set_per_attempt_and_orders_reads() -> None:
    world = build_fixed_run()
    attempt = world.attempts[("epics[0].stories[0].plan", 1)]
    world.fact_sets.add(
        FactSet(
            id=uuid4(),
            attempt_id=attempt.id,
            run_id=RUN_ID,
            extractor="newer",
            extractor_version=1,
            read_at=attempt.ended_at + timedelta(days=1),  # type: ignore[operator]
            status="ok",
        ),
        AttemptFacts(),
    )
    inputs = load_inputs(world.ports, RUN_ID)
    first = next(a for a in inputs.attempts if a.attempt.id == attempt.id)
    assert first.fact_set is not None and first.fact_set.extractor == "newer"
    assert first.facts == AttemptFacts()
    assert [a.row.seq for a in inputs.attempts] == sorted(a.row.seq for a in inputs.attempts)
    assert len(inputs.attempts) == ATTEMPTS
    assert inputs.now == world.ports.clock.now()


def test_load_inputs_refuses_an_unknown_run() -> None:
    world = build_fixed_run()
    with pytest.raises(LookupError):
        load_inputs(world.ports, UUID(int=999))


def test_an_attempt_with_no_usable_fact_set_has_no_facts() -> None:
    world = build_fixed_run()
    world.fact_sets.sets.clear()
    inputs = load_inputs(world.ports, RUN_ID)
    assert all(a.fact_set is None and a.facts is None for a in inputs.attempts)
    assert live_values(world.ports, RUN_ID)


def test_compute_runs_every_registered_method_in_key_order() -> None:
    row = make_row()
    inputs = make_inputs([row], [make_ai(row)])
    seen: list[str] = []
    saved = dict(REGISTRY)
    try:
        for key in saved:
            REGISTRY[key] = lambda i, key=key: seen.append(key) or []  # type: ignore[misc]
        assert compute(inputs) == []
    finally:
        REGISTRY.update(saved)
    assert seen == sorted(saved)


def test_stories_done_needs_every_row_done_or_skipped_and_one_done() -> None:
    rows = [
        make_row("stories[0].a", 1),
        make_row("stories[0].b", 2, status="skipped"),
        make_row("stories[1].a", 3, status="skipped"),
        make_row("stories[2].a", 4, status="error"),
        make_row("plain", 5),
    ]
    inputs = make_inputs(rows, [])
    assert set(story_rows(inputs)) == {"stories[0]", "stories[1]", "stories[2]"}
    assert stories_done(inputs) == (1, 3)


def test_a_park_ends_at_the_next_operator_signal_or_lifecycle_record() -> None:
    records = [
        make_record("blocked", 100, path="a"),
        make_record("answer", 160, "operator", "a"),
        make_record("checkpoint", 200, path="b"),
        make_record("done", 500),
        make_record("verify_failed", 600, path="c"),
    ]
    spans = park_spans(make_inputs([make_row()], [], records))
    assert [(s.position, s.kind, int(s.seconds)) for s in spans] == [
        (1, "blocked", 60),
        (3, "checkpoint", 300),
        (5, "verify_failed", 400),
    ]


def test_an_open_park_ends_at_now_on_a_live_run() -> None:
    run = make_run(ended_at=None)
    spans = park_spans(make_inputs([make_row()], [], [make_record("blocked", 1000, path="a")], run))
    assert int(spans[0].seconds) == OPEN_FOR


def test_retry_records_split_by_kind_and_actor() -> None:
    records = [
        make_record("retry_auto", 1, path="a"),
        make_record("redispatch", 2, path="v"),
        make_record("retry", 3, "operator", "a"),
        make_record("retry", 4, "chat", "a"),
    ]
    found = retry_records(make_inputs([make_row()], [], records))
    assert {k: len(v) for k, v in found.items()} == {
        "retry_auto": 1,
        "redispatch": 1,
        "operator": 1,
    }


def test_created_attempts_follow_the_attribution_rules() -> None:
    impl, verify, later = (
        make_row("impl", 1),
        make_row("verify", 2, kind="shell"),
        make_row("late", 3),
    )
    a1 = make_ai(impl, make_attempt(impl, 1, started_at=at(0)))
    a2 = make_ai(impl, make_attempt(impl, 2, started_at=at(300)))
    a3 = make_ai(impl, make_attempt(impl, 3, started_at=at(900)))
    v2 = make_ai(verify, make_attempt(verify, 2, started_at=at(400)))
    l2 = make_ai(later, make_attempt(later, 2, started_at=at(350)))
    records = [
        make_record("redispatch", 200, path="verify"),
        make_record("retry_auto", 1, path="impl"),
        make_record("retry", 2, "operator", "impl"),
        make_record("redispatch", 1, path="nowhere"),
        make_record("retry_auto", 5, path="empty"),
    ]
    inputs = make_inputs([impl, verify, later], [a1, a2, a3, v2, l2], records)
    found = created_attempts(inputs)
    assert found["redispatch"] == [a2, v2]
    assert found["retry_auto"] == [a2]
    assert found["operator"] == [a2]


def test_two_records_before_one_attempt_count_it_once() -> None:
    row = make_row("impl")
    ai = make_ai(row, make_attempt(row, 2, started_at=at(50)))
    records = [make_record("retry_auto", 1, path="impl"), make_record("retry_auto", 2, path="impl")]
    assert created_attempts(make_inputs([row], [ai], records))["retry_auto"] == [ai]
    redispatches = [
        make_record("redispatch", 1, path="impl"),
        make_record("redispatch", 2, path="impl"),
    ]
    assert created_attempts(make_inputs([row], [ai], redispatches))["redispatch"] == [ai]


def test_an_attempt_without_a_start_creates_nothing() -> None:
    row = make_row("impl")
    ai = make_ai(row, make_attempt(row, 2, started_at=None))
    found = created_attempts(make_inputs([row], [ai], [make_record("retry_auto", 1, path="impl")]))
    assert found["retry_auto"] == []
    assert Decimal(0) == Decimal(0)
