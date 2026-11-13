"""`code.test_first_order@1`: the order stories wrote tests and production code (epic 6 story 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.methods.code_test_first import first_order_values, outcome_of
from orchestrator.application.metrics.values import NO_STORY_FRAME, value_at
from orchestrator.domain.entities.facts import AttemptFacts, EventFact
from tests.unit.application.metrics_builders import make_ai, make_attempt, make_inputs, make_row

METRIC = "code.test_first_order"
FRAME = "stories[0]"
TEST_FILE = "tests/unit/test_x.py"
PROD_FILE = "src/x.py"
FAILING = 1


def clock(hh_mm: str) -> datetime:
    hour, minute = hh_mm.split(":")
    return datetime(2026, 11, 13, int(hour), int(minute), tzinfo=UTC)


def write(hh_mm: str, path: str) -> EventFact:
    return EventFact(at=clock(hh_mm), conversation="main", kind="write", path=path)


def run(hh_mm: str, exit_code: int | None) -> EventFact:
    return EventFact(
        at=clock(hh_mm), conversation="main", kind="test_run", command="pytest", exit_code=exit_code
    )


def story(*events: EventFact, frame: str = FRAME, story_id: str = "story-a"):  # type: ignore[no-untyped-def]
    row = make_row(f"{frame}.implement", story_id=story_id)
    return row, make_ai(row, facts=AttemptFacts(events=events))


def outcomes(*stories):  # type: ignore[no-untyped-def]
    rows = [row for row, _ in stories]
    return first_order_values(make_inputs(rows, [ai for _, ai in stories]))


def story_outcome(values, frame: str = FRAME) -> str:  # type: ignore[no-untyped-def]
    [found] = [v for v in values if v.scope_type == "story" and v.scope_key == frame]
    return found.source


def test_the_method_is_registered() -> None:
    assert REGISTRY[f"{METRIC}@1"] is first_order_values


def test_a_test_write_a_failing_run_then_a_production_write_is_test_first() -> None:  # AC7
    events = (
        write("10:00", TEST_FILE),
        run("10:02", FAILING),
        write("10:05", PROD_FILE),
    )

    values = outcomes(story(*events))

    assert story_outcome(values) == "test_first"
    [row] = [v for v in values if v.scope_type == "story"]
    assert (row.value_num, row.unit, row.scope_label, row.method_id) == (
        1,
        "story",
        "story-a",
        f"{METRIC}@1",
    )


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ((write("10:00", PROD_FILE), write("10:05", TEST_FILE)), "test_after"),
        ((write("10:00", PROD_FILE),), "test_after"),
        ((write("10:00", TEST_FILE), write("10:05", PROD_FILE)), "test_with_code"),
        (
            (write("10:00", TEST_FILE), run("10:02", 0), write("10:05", PROD_FILE)),
            "test_with_code",
        ),
        (
            (write("10:00", TEST_FILE), run("10:02", None), write("10:05", PROD_FILE)),
            "test_with_code",
        ),
        (
            (write("10:00", TEST_FILE), write("10:05", PROD_FILE), run("10:06", FAILING)),
            "test_with_code",
        ),
        ((write("10:00", TEST_FILE), write("10:00", PROD_FILE)), "test_with_code"),
        (
            (write("10:00", TEST_FILE), write("10:03", PROD_FILE), write("10:04", TEST_FILE)),
            "test_with_code",
        ),
        ((write("10:00", TEST_FILE),), "test_with_code"),
        (
            (write("10:00", "tests/e2e/flow.spec.ts"), run("10:01", 2), write("10:02", PROD_FILE)),
            "test_first",
        ),
        ((), "not_readable"),
        ((write("10:00", "README.md"), write("10:01", "pyproject.toml")), "not_readable"),
        ((run("10:00", FAILING),), "not_readable"),
    ],
)
def test_the_decision_rule_branches(events: tuple[EventFact, ...], expected: str) -> None:
    assert outcome_of(events) == expected


def test_a_write_without_a_path_is_ignored() -> None:
    bare = EventFact(at=clock("10:00"), conversation="main", kind="write")

    assert outcome_of((bare,)) == "not_readable"


def test_events_of_every_attempt_of_the_story_are_read_together() -> None:
    row = make_row(f"{FRAME}.implement", story_id="a")
    first = make_ai(
        row,
        make_attempt(row, 1),
        facts=AttemptFacts(events=(write("10:00", TEST_FILE), run("10:01", 1))),
    )
    second = make_ai(
        row, make_attempt(row, 2), facts=AttemptFacts(events=(write("10:05", PROD_FILE),))
    )

    values = first_order_values(make_inputs([row], [first, second]))

    assert story_outcome(values) == "test_first"


def test_an_attempt_of_another_story_is_not_read() -> None:
    mine = story(write("10:05", PROD_FILE))
    other = story(write("10:00", TEST_FILE), frame="stories[1]", story_id="b")

    values = outcomes(mine, other)

    assert story_outcome(values) == "test_after"
    assert story_outcome(values, "stories[1]") == "test_with_code"


def test_an_attempt_with_no_facts_reads_as_no_events() -> None:
    row = make_row(f"{FRAME}.implement", story_id="a")

    values = first_order_values(make_inputs([row], [make_ai(row)]))

    assert story_outcome(values) == "not_readable"


def test_a_run_of_no_events_is_every_story_not_readable_at_one_hundred_percent() -> None:  # AC8
    values = outcomes(story(), story(frame="stories[1]", story_id="b"))

    counts = {
        t: value_at(values, METRIC, "run", "run", t).value_num
        for t in ("test_first", "test_with_code", "test_after", "not_readable")
    }
    assert counts == {"test_first": 0, "test_with_code": 0, "test_after": 0, "not_readable": 2}
    share = value_at(values, METRIC, "run", "run", "not_readable_share")
    assert (share.value_num, share.unit) == (Decimal("100.00"), "%")
    assert value_at(values, METRIC, "run", "run", "not_readable").unit == "stories"


def test_the_run_counts_each_outcome_and_the_share_rounds_to_hundredths() -> None:
    first = story(write("10:00", TEST_FILE), run("10:01", 1), write("10:02", PROD_FILE))
    after = story(write("10:00", PROD_FILE), frame="stories[1]", story_id="b")
    blind = story(frame="stories[2]", story_id="c")

    values = outcomes(first, after, blind)

    assert value_at(values, METRIC, "run", "run", "test_first").value_num == 1
    assert value_at(values, METRIC, "run", "run", "test_after").value_num == 1
    assert value_at(values, METRIC, "run", "run", "test_with_code").value_num == 0
    assert value_at(values, METRIC, "run", "run", "not_readable_share").value_num == Decimal(
        "33.33"
    )


def test_a_run_with_no_story_frame_says_so() -> None:
    row = make_row("build")

    [value] = first_order_values(make_inputs([row], [make_ai(row)]))

    assert (value.scope_type, value.value_num, value.missing) == ("run", None, NO_STORY_FRAME)


def test_a_run_with_no_rows_has_nothing_to_say() -> None:
    assert first_order_values(make_inputs([], [])) == []
