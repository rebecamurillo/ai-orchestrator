"""`park_row_kind_of` (4.9): the parked row's `kind`, for `RunSummaryOut.admitted_signals`.

`get_run` and `RunReadPorts` are 4.4's own; this is the one lookup 4.9 adds beside them, so
`GET /runs/{id}` (`api/routers/run.py::get`) and `GET /runs/{id}/signals`
(`api/routers/signals.py::get_signals`) can pass the row's `kind` to
`RunSummaryOut.of(run, park_row_kind=...)` without either handler reaching a repository
directly.
"""

from __future__ import annotations

from orchestrator.application.use_cases.create_run import RunReadPorts, park_row_kind_of
from tests.unit.application.writer_fixtures import EPIC_PLAN, a_world

BUILD = "stories[0].build"


def test_none_for_a_run_that_is_not_parked() -> None:
    world = a_world("running", EPIC_PLAN, {})
    ports = RunReadPorts(runs=world.ports.runs, steps=world.ports.steps)

    assert park_row_kind_of(ports, world.run) is None


def test_none_when_no_step_repository_was_wired() -> None:
    """`test_run_router.py` (4.4) constructs `RunReadPorts(runs=...)` alone — `steps`
    defaults to `None`, and this reads that conservatively rather than raising."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="waiting",
    )
    ports = RunReadPorts(runs=world.ports.runs)

    assert park_row_kind_of(ports, world.run) is None


def test_the_parked_rows_own_kind_once_needs_you_and_steps_are_both_there() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="waiting",
    )
    ports = RunReadPorts(runs=world.ports.runs, steps=world.ports.steps)

    assert park_row_kind_of(ports, world.run) == "agent"


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

    assert park_row_kind_of(ports, world.run) is None
