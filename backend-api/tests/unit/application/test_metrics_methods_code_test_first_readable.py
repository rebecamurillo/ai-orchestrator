"""`readable` and `stories` run rows of `code.test_first_order@1` (epic 6 story 4, AC3)."""

from __future__ import annotations

from orchestrator.application.metrics.methods.code_test_first import first_order_values
from orchestrator.domain.entities.facts import AttemptFacts
from tests.unit.application.metrics_builders import make_ai, make_inputs, make_row
from tests.unit.application.test_metrics_methods_code_test_first import (
    FAILING,
    PROD_FILE,
    TEST_FILE,
    run,
    write,
)

METRIC = "code.test_first_order"
READABLE = 6
STORIES = 8


def _story(n: int, *events):  # type: ignore[no-untyped-def]
    row = make_row(f"stories[{n}].implement", story_id=f"s{n}")
    return row, make_ai(row, facts=AttemptFacts(events=events))


FIRST = (write("10:00", TEST_FILE), run("10:02", FAILING), write("10:05", PROD_FILE))
NONE: tuple = ()


def _rows(values, source):  # type: ignore[no-untyped-def]
    [found] = [v for v in values if v.scope_type == "run" and v.source == source]
    return found


def test_readable_and_stories_are_stored_beside_the_outcomes() -> None:
    stories = [_story(n, *FIRST) for n in range(4)]
    stories += [_story(n, write("10:00", TEST_FILE)) for n in range(4, 6)]
    stories += [_story(n, *NONE) for n in range(6, 8)]

    values = first_order_values(make_inputs([r for r, _ in stories], [a for _, a in stories]))

    readable, total = _rows(values, "readable"), _rows(values, "stories")
    assert (readable.value_num, total.value_num) == (READABLE, STORIES)
    assert (readable.unit, total.unit, readable.method_id) == ("stories", "stories", f"{METRIC}@1")


def test_no_readable_story_stores_zero() -> None:
    stories = [_story(n, *NONE) for n in range(2)]

    values = first_order_values(make_inputs([r for r, _ in stories], [a for _, a in stories]))

    assert (_rows(values, "readable").value_num, _rows(values, "stories").value_num) == (0, 2)
