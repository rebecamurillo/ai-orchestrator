"""A stop offers *Skip step* only where `validate` would admit it (Operator, 2026-09-26).

`VALID["skip_step"]` carries `row_statuses={blocked, checkpoint, error}` — the three the step
machine has a `skip` edge from — and `validate` enforces it. `admitted_signals(park_kind,
row_kind)` cannot see a row status at all, so on its own it would offer *Skip step* at a park
taken after a row ended `done` and the POST would come back 409. The step-handling spec names
that exact stop as one of the two Skip step cannot reach ("a budget park taken after a row
ended `done`", `stories.yaml` story 1); this is the offer being narrowed to match, so the
Run detail stops advertising an action the server refuses.

`run_admitted_signals` takes the parked row's status the way it already takes its kind: the
callers that look the row up pass it, and the list view that looks up neither keeps the coarse
answer its own docstring describes.
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules.signals import VALID, run_admitted_signals
from orchestrator.domain.statuses import STEP_STATUSES
from tests.unit.application.writer_fixtures import build_run

BUILD = "stories[0].build"

#: The three `skip_step` is admissible on, read off the table rather than restated, so this
#: test follows `VALID` if the step machine ever gains or loses a skippable status.
SKIPPABLE = VALID["skip_step"].row_statuses


def test_a_budget_park_on_a_row_that_ended_done_does_not_offer_skip_step() -> None:
    """The stop PRD §4.6 gives a raise and a cancel: `budget_second_record` stamps the park
    onto the row that has just finished, so there is nothing left on it to skip."""
    run = build_run(status="needs_you", park_kind="budget", park_path=BUILD)

    assert run_admitted_signals(run, "agent", park_row_status="done") == (
        "budget_raise",
        "cancel",
    )


@pytest.mark.parametrize("row_status", sorted(SKIPPABLE or ()))
def test_a_park_on_a_row_the_step_machine_can_skip_offers_skip_step(row_status: str) -> None:
    run = build_run(status="needs_you", park_kind="budget", park_path=BUILD)

    assert "skip_step" in run_admitted_signals(run, "agent", park_row_status=row_status)


@pytest.mark.parametrize(
    "row_status", sorted(status for status in STEP_STATUSES if status not in (SKIPPABLE or ()))
)
def test_no_other_row_status_offers_skip_step(row_status: str) -> None:
    """The narrowing is `validate`'s own column, not a special case for `done`: every status
    the step machine has no `skip` edge from is refused, so none of them is offered."""
    run = build_run(status="needs_you", park_kind="timeout", park_path=BUILD)

    assert "skip_step" not in run_admitted_signals(run, "agent", park_row_status=row_status)


def test_the_narrowing_touches_no_other_signal() -> None:
    """Only `skip_step` reads the row status; what the stop otherwise offers is unchanged."""
    run = build_run(status="needs_you", park_kind="verify_failed", park_path=BUILD)

    done = run_admitted_signals(run, "shell", park_row_status="done")
    errored = run_admitted_signals(run, "shell", park_row_status="error")

    assert done == tuple(kind for kind in errored if kind != "skip_step")


def test_a_row_status_that_was_not_looked_up_keeps_the_coarse_answer() -> None:
    """`RunSummaryOut`'s list view looks up neither kind nor status; it answers as it did
    before this narrowing, and nothing it feeds renders a signal control (the Run detail's
    own `admitted_signals` is what `StopBody` reads)."""
    run = build_run(status="needs_you", park_kind="budget", park_path=BUILD)

    assert "skip_step" in run_admitted_signals(run, None)
