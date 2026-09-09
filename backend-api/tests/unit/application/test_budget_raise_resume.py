"""What a raised budget puts back on the queue (story 6-6, FR-17, AD-8, AD-13).

Separate from `test_budget_raise_signal.py` because this is the half that was **broken**,
not merely unreachable. `signal_effects.py::_budget_raise` wrote `run.budget_usd` and let
`signal_run` move the Run to `running` — and then queued nothing at all.
`use_cases/walk.py::next_row` finds work three ways: `first_queued`, a row a signal left
`running`, and, only while every row is `planned`/`done`/`skipped`, the plan's first
`planned` row.

- A park on a **`done`** row satisfied the third by accident, so that case looked fine.
- A park on an **`error`** row — FR-17's retry path, where `steps/agent_tail.py::
  _spend_and_budget` parks `budget` on top of the status the row reached — satisfied none of
  them. `next_row` answered `None`, `close_run` read that as a stall, and the Run parked
  `internal`: a stop admitting nothing but `cancel`, reached by raising a budget.

So each test below asserts the *row*, and the `error` one asserts it against `walk.py`'s own
`next_row` rather than only against the repository, because "the row is queued" and "the walk
finds it" are the two halves that came apart.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from orchestrator.application.rules.signals import BUDGET_KEY
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.application.use_cases.walk import WalkPorts, next_row
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
COMMIT_GUARD = "stories[0].commit-guard"
LINK = "link"
DONE_BEFORE: dict[str, Any] = {
    "plan": "done",
    "checkout": "done",
    "baseline": "done",
    "stories[0].sync": "done",
}


def parked(row_status: str, path: str = BUILD, **extra_statuses: str) -> World:
    statuses: dict[str, Any] = {**DONE_BEFORE, path: row_status, **extra_statuses}
    return a_world(
        "needs_you",
        EPIC_PLAN,
        statuses,
        park_kind="budget",
        park_path=path,
        park_reason="budget $9.00 / $5.00",
        spend_usd=Decimal("9"),
        budget_usd=Decimal("5"),
    )


def raise_to(world: World, amount: str = "60") -> None:
    ports = SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir="/work",
        read_environment=lambda _run_id: None,
    )
    handle_signal(ports, world.run.id, Signal(kind="budget_raise", payload={BUDGET_KEY: amount}))


def test_a_park_on_an_error_row_re_queues_that_row() -> None:
    """AD-13's retry path: the row the dispatch left `error` runs again as a new Attempt."""
    world = parked("error")

    raise_to(world)

    assert world.status_of(BUILD) == "queued"
    assert world.stored_run().status == "running"


def test_the_walk_then_finds_that_row_rather_than_stalling() -> None:
    """The regression itself: before this story `next_row` answered `None` here, and
    `close_run` parked the Run `internal` — a stop that admits nothing but `cancel`."""
    world = parked("error")
    raise_to(world)

    seq = next_row(WalkPorts(writers=world.ports, step=None), world.run.id)  # type: ignore[arg-type]

    assert seq == world.row(BUILD).seq


def test_a_park_on_a_done_row_queues_the_next_row_instead() -> None:
    """The row is finished, so the frame's `verify` is what the walker continues at."""
    world = parked("done")

    raise_to(world)

    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"


def test_a_park_on_a_done_row_steps_over_rows_a_skip_already_settled() -> None:
    """`resume_from`'s own rule: the first row from the parked one on that is unfinished."""
    world = parked("done", **{VERIFY: "skipped"})

    raise_to(world)

    assert world.status_of(VERIFY) == "skipped"
    assert world.status_of(COMMIT_GUARD) == "queued"


def test_a_park_on_the_last_row_of_the_plan_ends_the_run() -> None:
    """Nothing is left to queue, so the Run reaches `done` rather than resuming into a stall."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        dict.fromkeys([path for path, _ in EPIC_PLAN], "done"),
        park_kind="budget",
        park_path=LINK,
        park_reason="budget $9.00 / $5.00",
        spend_usd=Decimal("9"),
        budget_usd=Decimal("5"),
    )

    raise_to(world)

    assert world.stored_run().status == "done"


def test_a_run_level_park_queues_nothing_and_leaves_the_plan_to_start_itself() -> None:
    """`Park.path` is optional; a Run parked on no row has none to resume from, and
    `next_row`'s own "start the plan" branch is what picks the first `planned` row up."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {},
        park_kind="budget",
        park_reason="budget $9.00 / $5.00",
        spend_usd=Decimal("9"),
        budget_usd=Decimal("5"),
    )

    raise_to(world)

    assert world.stored_run().status == "running"
    assert next_row(WalkPorts(writers=world.ports, step=None), world.run.id) == 1  # type: ignore[arg-type]
