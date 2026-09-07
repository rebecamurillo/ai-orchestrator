"""`run_admitted_signals` and `row_at` (4.9): the two small additions `application/rules/
signals.py` makes beside the AD-13 table 4.5 already built.

`admitted_signals(park_kind, row_kind)` (4.5) answers "what does this stop admit" and is
`test_signal_rules.py`'s own coverage; `run_admitted_signals(run, park_row_kind)` answers
the wider question `RunSummaryOut` needs — what does *this Run* offer right now, including
while it is not parked at all.
"""

from __future__ import annotations

from orchestrator.application.rules.signals import row_at, run_admitted_signals
from tests.unit.application.writer_fixtures import EPIC_PLAN, build_rows, build_run

BUILD = "stories[0].build"


def test_a_terminal_run_admits_nothing() -> None:
    for status in ("done", "failed", "cancelled"):
        run = build_run(status=status)

        assert run_admitted_signals(run, None) == ()


def test_a_queued_or_running_run_admits_only_cancel() -> None:
    for status in ("queued", "running"):
        run = build_run(status=status)

        assert run_admitted_signals(run, None) == ("cancel",)


def test_a_parked_run_with_no_park_kind_admits_nothing() -> None:
    """A stored Run should never reach `needs_you` with `park_kind` unset (AD-8 writes them
    together), but this reads defensively rather than raising."""
    run = build_run(status="needs_you", park_kind=None)

    assert run_admitted_signals(run, None) == ()


def test_a_parked_run_delegates_to_admitted_signals_with_its_park_and_row_kind() -> None:
    run = build_run(status="needs_you", park_kind="push_rejected", park_path="push")

    assert run_admitted_signals(run, "git.push") == ("retry", "skip_epic", "cancel")


def test_a_parked_run_without_a_looked_up_row_kind_answers_conservatively() -> None:
    """`RunSummaryOut`'s list view does not look the row up — `""` never matches a
    `row_kinds` set, so a kind like `answer` that needs `agent` is never over-reported."""
    run = build_run(status="needs_you", park_kind="checkpoint", park_path="stories[1].after")

    admitted = run_admitted_signals(run, None)

    assert "answer" not in admitted
    assert "continue" in admitted


def test_row_at_finds_the_row_a_path_names() -> None:
    run_id = build_run().id
    rows = build_rows(run_id, EPIC_PLAN)

    found = row_at(rows, BUILD)

    assert found is not None
    assert found.path == BUILD


def test_row_at_answers_none_for_a_path_named_by_nothing() -> None:
    run_id = build_run().id
    rows = build_rows(run_id, EPIC_PLAN)

    assert row_at(rows, "no-such-row") is None
    assert row_at(rows, None) is None
