"""`park_row_of`: the parked row itself, not just its `kind` (Operator, 2026-09-26).

`park_row_kind_of` (4.9) answered the one field `RunSummaryOut` needed then. The `skip_step`
offer needs a second one off the same row — its `status`, because `validate` admits a skip
only from `blocked`, `checkpoint` or `error` — so the lookup now hands the row back and
`api/routers/run.py::get` reads both fields off one read. `park_row_kind_of` keeps its own
contract and its own tests (`test_park_row_kind_of.py`); this covers what it delegates to.
"""

from __future__ import annotations

from orchestrator.application.use_cases.create_run import RunReadPorts, park_row_of
from orchestrator.domain.entities.run import Run
from tests.unit.application.writer_fixtures import EPIC_PLAN, a_world

BUILD = "stories[0].build"


def _parked(row_status: str = "blocked") -> tuple[RunReadPorts, Run]:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: row_status},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="waiting",
    )
    return RunReadPorts(runs=world.ports.runs, steps=world.ports.steps), world.run


def test_the_parked_row_carries_both_the_kind_and_the_status_the_offer_needs() -> None:
    ports, run = _parked("blocked")

    row = park_row_of(ports, run)

    assert row is not None
    assert row.path == BUILD
    assert row.kind == "agent"
    assert row.status == "blocked"


def test_a_row_that_ended_done_is_returned_with_that_status() -> None:
    """The `budget` park's own shape: `budget_second_record` stamps the park onto the row
    that has just finished, and the status is what stops *Skip step* being offered there."""
    ports, run = _parked("done")

    row = park_row_of(ports, run)

    assert row is not None
    assert row.status == "done"


def test_none_for_a_run_that_is_not_parked() -> None:
    world = a_world("running", EPIC_PLAN, {})
    ports = RunReadPorts(runs=world.ports.runs, steps=world.ports.steps)

    assert park_row_of(ports, world.run) is None


def test_none_when_no_step_repository_was_wired() -> None:
    ports, run = _parked()

    assert park_row_of(RunReadPorts(runs=ports.runs), run) is None


def test_none_when_the_parked_path_names_no_stored_row() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {},
        park_kind="blocked",
        park_path="no-such-row",
        park_reason="waiting",
    )
    ports = RunReadPorts(runs=world.ports.runs, steps=world.ports.steps)

    assert park_row_of(ports, world.run) is None
