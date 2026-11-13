"""Time methods over small inputs (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.methods import time
from orchestrator.application.metrics.values import value_at
from tests.unit.application.metrics_builders import (
    at,
    make_ai,
    make_attempt,
    make_inputs,
    make_record,
    make_row,
    make_run,
)


def test_a_run_without_a_start_reads_not_recorded_for_wall_and_machine() -> None:
    inputs = make_inputs([make_row()], [], run=make_run(started_at=None))
    assert time.wall(inputs)[0].missing == "not recorded"
    assert time.machine(inputs)[0].missing == "not recorded"
    assert time.run_wall(inputs) is None


def test_a_live_run_reads_now_for_its_end() -> None:
    inputs = make_inputs([make_row()], [], run=make_run(ended_at=None))
    assert time.run_wall(inputs) == Decimal(2000)


def test_a_frame_wall_uses_now_for_an_unfinished_attempt_of_a_live_run() -> None:
    row = make_row("stories[0].a")
    ai = make_ai(row, make_attempt(row, started_at=at(100), ended_at=None))
    walls = time.frame_walls(make_inputs([row], [ai], run=make_run(ended_at=None)))
    assert set(walls.values()) == {Decimal(1900)}
    ended = time.frame_walls(make_inputs([row], [ai]))
    assert set(ended.values()) == {Decimal(900)}
    unstarted = make_ai(row, make_attempt(row, started_at=None, ended_at=None))
    assert time.frame_walls(make_inputs([row], [unstarted])) == {}


def test_attempt_time_is_partial_when_an_attempt_has_no_end() -> None:
    row = make_row()
    done = make_ai(row, make_attempt(row, 1))
    open_ = make_ai(row, make_attempt(row, 2, ended_at=None))
    run = value_at(
        time.attempt_seconds(make_inputs([row], [done, open_])),
        "time.attempt_seconds",
        "run",
        "run",
    )
    assert (run.value_num, run.missing, run.partial_n, run.partial_m) == (
        Decimal(100),
        "partial",
        1,
        2,
    )


def test_by_role_and_operator_active() -> None:
    row = make_row()
    inputs = make_inputs([row], [make_ai(row, role="plan")], run=make_run(active_seconds=42))
    assert value_at(time.by_role(inputs), "time.by_role", "role", "plan").value_num == Decimal(100)
    assert time.operator_active(inputs)[0].value_num == Decimal(42)


def test_wall_stats_of_stories_and_epics() -> None:
    rows = [make_row(f"epics[0].stories[{i}].a", i + 1) for i in range(3)]
    spans = [(0, 100), (0, 300), (0, 200)]
    ais = [
        make_ai(r, make_attempt(r, started_at=at(s), ended_at=at(e)))
        for r, (s, e) in zip(rows, spans, strict=True)
    ]
    inputs = make_inputs(rows, ais)
    stories = time.story_wall_stats(inputs)
    for source, expected in (("average", 200), ("median", 200), ("longest", 300)):
        assert value_at(
            stories, "time.story_wall_stats", "run", "run", source
        ).value_num == Decimal(expected)
        assert value_at(
            stories, "time.story_wall_stats", "epic", "epics[0]", source
        ).value_num == Decimal(expected)
    epics = time.epic_wall_stats(inputs)
    assert value_at(epics, "time.epic_wall_stats", "run", "run", "longest").value_num == Decimal(
        300
    )


def test_wall_stats_without_frames_say_so() -> None:
    inputs = make_inputs([make_row()], [make_ai(make_row())])
    assert time.story_wall_stats(inputs)[0].missing == "n/a — template has no story frame"
    assert time.epic_wall_stats(inputs)[0].missing == "n/a — template has no epic frame"


def test_retries_and_failures_time() -> None:
    row = make_row("stories[0].a")
    first = make_ai(row, make_attempt(row, 1, status="error"))
    second = make_ai(row, make_attempt(row, 2, started_at=at(200), ended_at=at(500)))
    inputs = make_inputs(
        [row], [first, second], [make_record("retry_auto", 150, path="stories[0].a")]
    )
    assert value_at(time.retries(inputs), "time.retries", "run", "run").value_num == Decimal(300)
    assert value_at(time.failures(inputs), "time.failures", "run", "run").value_num == Decimal(100)


def test_machine_time_of_a_frame_counts_only_the_parks_inside_its_wall() -> None:
    a = make_row("epics[0].stories[0].a", seq=1)
    gate = make_row("epics[0].stories[0].gate", seq=2, kind="checkpoint")
    ai = make_ai(a, make_attempt(a, started_at=at(0), ended_at=at(600)))
    records = [
        make_record("blocked", 100, path=a.path),
        make_record("continue", 300, actor="operator", path=a.path),
        make_record("checkpoint", 600, path=gate.path),
        make_record("continue", 900, actor="operator", path=gate.path),
    ]
    values = time.machine(make_inputs([a, gate], [ai], records))
    story = value_at(values, "time.machine", "story", "epics[0].stories[0]")
    epic = value_at(values, "time.machine", "epic", "epics[0]")
    assert (story.value_num, epic.value_num) == (Decimal(400), Decimal(400))
    run = value_at(values, "time.machine", "run", "run")
    assert run.value_num == Decimal(500)


def test_a_spec_edit_during_a_park_does_not_end_it() -> None:
    row = make_row("a")
    records = [
        make_record("blocked", 100, path="a"),
        make_record("spec_edit", 200, actor="operator", path="a"),
        make_record("continue", 700, actor="operator", path="a"),
    ]
    values = time.parked(make_inputs([row], [], records))
    assert value_at(values, "time.parked", "run", "run").value_num == Decimal(600)
