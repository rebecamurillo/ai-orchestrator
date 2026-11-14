"""Process methods over small inputs (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.methods import process
from orchestrator.application.metrics.values import value_at
from tests.unit.application.metrics_builders import (
    make_ai,
    make_attempt,
    make_inputs,
    make_record,
    make_row,
)


def test_attempts_per_story_without_a_story_frame_says_so() -> None:
    values = process.attempts_per_story(make_inputs([make_row()], []))
    assert [(v.scope_key, v.missing) for v in values] == [("", "n/a — template has no story frame")]


def test_attempts_per_story_gives_each_story_and_the_average_and_maximum() -> None:
    rows = [make_row("epics[0].stories[0].a", 1), make_row("epics[0].stories[1].a", 2)]
    ais = [make_ai(rows[0], make_attempt(rows[0], n)) for n in (1, 2, 3)] + [make_ai(rows[1])]
    values = process.attempts_per_story(make_inputs(rows, ais))
    assert value_at(
        values, "process.attempts_per_story", "story", "epics[0].stories[0]"
    ).value_num == Decimal(3)
    assert value_at(
        values, "process.attempts_per_story", "run", "run", "average"
    ).value_num == Decimal(2)
    assert value_at(
        values, "process.attempts_per_story", "epic", "epics[0]", "maximum"
    ).value_num == Decimal(3)


def test_a_story_without_attempts_counts_zero_attempts() -> None:
    row = make_row("stories[0].a", status="skipped")
    values = process.attempts_per_story(make_inputs([row], []))
    assert value_at(
        values, "process.attempts_per_story", "story", "stories[0]"
    ).value_num == Decimal(0)


def test_a_retry_record_on_an_unknown_row_is_not_counted() -> None:
    row = make_row("a")
    records = [make_record("retry_auto", 1, path="gone"), make_record("retry_auto", 2, path="a")]
    values = process.retries(make_inputs([row], [], records))
    assert value_at(values, "process.retries", "run", "run", "retry_auto").value_num == Decimal(1)
    assert value_at(values, "process.retries", "run", "run", "redispatch").value_num == Decimal(0)


def test_failures_count_attempts_not_done_or_skipped() -> None:
    row = make_row()
    ais = [
        make_ai(row, make_attempt(row, n, status=s))
        for n, s in enumerate(("done", "error", "blocked"), 1)
    ]
    assert value_at(
        process.failures(make_inputs([row], ais)), "process.failures", "run", "run"
    ).value_num == Decimal(2)


def test_parks_are_counted_by_kind_and_interventions_by_actor() -> None:
    records = [
        make_record("blocked", 1, path="a"),
        make_record("answer", 2, "operator", "a"),
        make_record("blocked", 3, path="a"),
        make_record("checkpoint", 4, path="a"),
    ]
    inputs = make_inputs([make_row()], [], records)
    parks = process.parks(inputs)
    assert value_at(parks, "process.parks", "run", "run").value_num == Decimal(3)
    assert value_at(parks, "process.parks", "run", "run", "blocked").value_num == Decimal(2)
    assert process.interventions(inputs)[0].value_num == Decimal(1)


def test_gate_first_pass_counts_gates_that_passed_first() -> None:
    ok = make_row("v1", 1, role="verify")
    bad = make_row("v2", 2, role="e2e")
    untouched = make_row("v3", 3, role="spec-gate")
    ais = [
        make_ai(ok, make_attempt(ok, 1)),
        make_ai(bad, make_attempt(bad, 1, status="error")),
        make_ai(bad, make_attempt(bad, 2)),
    ]
    values = process.gate_first_pass(make_inputs([ok, bad, untouched], ais))
    assert value_at(values, "process.gate_first_pass", "run", "run").value_num == Decimal(1)
    assert value_at(values, "process.gate_first_pass", "gate", "v1").value_num == Decimal(1)
    assert value_at(values, "process.gate_first_pass", "gate", "v2").value_num == Decimal(0)


def test_no_gate_row_reads_na() -> None:
    assert (
        process.gate_first_pass(make_inputs([make_row()], []))[0].missing
        == "n/a — no gate step ran"
    )


def test_an_epic_without_a_story_has_no_attempts_per_story_statistics() -> None:
    rows = [make_row("epics[0].stories[0].a", 1), make_row("epics[1].push", 2)]
    values = process.attempts_per_story(make_inputs(rows, [make_ai(rows[0])]))
    assert [v for v in values if v.scope_type == "epic" and v.scope_key == "epics[1]"] == []
