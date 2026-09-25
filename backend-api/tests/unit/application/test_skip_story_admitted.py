"""The re-baseline park's own offered set (6.4, FR-20, UX-DR10).

`apply_step_result` parks `verify_failed · re-baseline failed after skip` when a verify row
redispatches onto a target that was never run (AD-9) — which, after a `skip_story`, is the
`build` row the Operator just skipped. The brief's own rule for that stop is *Retry*, *Skip
epic*, *Cancel run*: a second Skip story has nothing left to skip and would merely re-queue
the row Retry re-queues.

Two things are asserted apart here, because they are two different questions. `admitted_
signals(park_kind, row_kind)` — PRD §4.6's column, frozen in `test_signal_rules.py` — is
unchanged: a `verify_failed` stop still offers Skip story. `run_admitted_signals(run, kind)`
is what a Run detail reads, and it is the one that narrows, on `run.park_reason`. And
`validate` narrows with neither: AD-13's table is keyed on the park kind, so posting the
signal there stays admissible.
"""

from __future__ import annotations

from orchestrator.application.rules.signals import (
    REBASELINE_FAILED,
    admitted_signals,
    run_admitted_signals,
    validate,
)
from orchestrator.application.use_cases.apply_step_result import REBASELINE_FAILED as FROM_WRITER
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import build_rows, build_run

VERIFY = "stories[0].verify"


def a_run(reason: str, park_kind: str = "verify_failed"):
    return build_run("needs_you", park_kind=park_kind, park_path=VERIFY, park_reason=reason)


def a_verify_row(run_id, status: str = "error"):
    rows = build_rows(run_id)
    row = next(entry for entry in rows if entry.path == VERIFY)
    return row.model_copy(update={"status": status})


def test_the_writer_and_the_table_name_the_same_sentence() -> None:
    """One definition: `apply_step_result` imports the reason it parks with from the rules
    module that reads it, so the two can never drift into a silent mismatch."""
    assert FROM_WRITER is REBASELINE_FAILED
    assert REBASELINE_FAILED == "re-baseline failed after skip"


def test_the_re_baseline_park_offers_retry_skip_epic_and_cancel() -> None:
    run = a_run(REBASELINE_FAILED)

    # story 1 (2026-09-25): skip_step admitted on every park kind.
    assert run_admitted_signals(run, "shell") == ("retry", "skip_step", "skip_epic", "cancel")


def test_an_ordinary_verify_failure_still_offers_skip_story() -> None:
    """The narrowing is the reason's, not the park kind's: PRD §4.6's `verify_failed` row is
    untouched for every other way that park is reached."""
    run = a_run("verify failed 2/2")

    # story 1 (2026-09-25): skip_step admitted on every park kind.
    assert run_admitted_signals(run, "shell") == (
        "retry",
        "skip_step",
        "skip_story",
        "skip_epic",
        "cancel",
    )


def test_the_prd_table_itself_is_not_narrowed() -> None:
    """`admitted_signals` answers from the park kind and the row kind alone and knows no
    reason — `test_signal_rules.py` pins it against PRD §4.6 and stays true."""
    assert "skip_story" in admitted_signals("verify_failed", "shell")


def test_another_park_kind_carrying_the_same_reason_is_narrowed_too() -> None:
    """The rule is stated over the reason, so it does not silently depend on the kind the
    only writer of that sentence happens to use today."""
    run = a_run(REBASELINE_FAILED, park_kind="timeout")

    assert "skip_story" not in run_admitted_signals(run, "shell")


def test_ad13_still_admits_the_signal_at_that_park() -> None:
    """What the stop *offers* and what the table *validates* are two rules (AD-13). A
    `skip_story` posted at a re-baseline park is applied, not refused: it re-queues the same
    verify row, which is exactly what the Operator asked for."""
    run = a_run(REBASELINE_FAILED)
    row = a_verify_row(run.id)

    rule = validate(run, row, Signal(kind="skip_story", payload={}))

    assert rule.run_event == "skip_story"
