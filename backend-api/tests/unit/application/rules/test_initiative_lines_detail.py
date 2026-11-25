"""The step token, files state and the two detail lines (story 6, epic 7; EXPERIENCE I3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from orchestrator.application.rules.initiative_lines import (
    StripFact,
    TrackFact,
    files_state,
    step_token,
    strip_line,
    workflow_line,
)
from orchestrator.application.use_cases.run_view_types import Progress
from tests.unit.initiative_fixtures import a_run

ENDED = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "forced", "cancelled", "expected"),
    [
        ("planned", False, True, "CAN"),
        ("running", False, True, "CAN"),
        ("waiting for her", False, True, "CAN"),
        ("done", False, True, "DON"),
        ("running", False, False, "RUN"),
        ("waiting for her", False, False, "BLK"),
        ("done", False, False, "DON"),
        ("failed", False, False, "ERR"),
        ("skipped", True, False, "SKP"),
        ("skipped", False, False, "DON"),
        ("planned", False, False, "QUE"),
    ],
)
def test_step_token(status: Any, forced: bool, cancelled: bool, expected: str) -> None:
    assert step_token(status, forced=forced, cancelled=cancelled) == expected


@pytest.mark.parametrize(
    ("status", "forced", "expected"),
    [
        ("done", False, "done"),
        ("running", False, "open"),
        ("waiting for her", False, "open"),
        ("planned", False, "to come"),
        ("skipped", True, "skipped, forced"),
        ("skipped", False, "done"),
        ("failed", False, "failed"),
    ],
)
def test_files_state(status: Any, forced: bool, expected: str) -> None:
    assert files_state(status, forced=forced) == expected


def strip(**overrides: Any) -> str:
    values: dict[str, Any] = {
        "status": "planned",
        "kind": "conversation",
        "is_merge": False,
        "forced": False,
        "reason": None,
        "ended_at": None,
        "file_names": (),
        "is_current": False,
        "attention": None,
        "round": 1,
        "turns": 0,
        "conflicts": 0,
        "position_in_workflow": 0,
        "previous_id": None,
        "previous_is_gate": False,
        "follows_current": False,
    }
    values.update(overrides)
    return strip_line(StripFact(**values))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"status": "done", "ended_at": ENDED, "file_names": ("PRD.md", "UX.md")},
            "closed 2026-11-24 · PRD.md, UX.md",
        ),
        ({"status": "done", "ended_at": ENDED}, "closed 2026-11-24"),
        ({"status": "done"}, "closed"),
        ({"status": "done", "is_merge": True, "ended_at": ENDED}, "merged 2026-11-24"),
        ({"status": "skipped", "forced": True, "ended_at": ENDED}, "skipped, forced · 21:30"),
        ({"status": "skipped", "forced": True}, "skipped, forced"),
        ({"status": "skipped", "reason": "not in this round"}, "not in this round"),
        ({"status": "skipped"}, "skipped"),
        (
            {"status": "waiting for her", "is_merge": True, "conflicts": 1},
            "conflict · 1 file · your turn",
        ),
        (
            {"status": "waiting for her", "is_merge": True, "conflicts": 2},
            "conflict · 2 files · your turn",
        ),
        (
            {"status": "failed", "kind": "automatic", "reason": "two open questions"},
            "two open questions",
        ),
        ({"status": "waiting for her", "reason": "step not closed"}, "needs you · step not closed"),
        ({"status": "waiting for her", "round": 2}, "round 2 · your turn"),
        ({"status": "waiting for her"}, "needs you"),
        ({"status": "failed", "reason": "agent exited 1"}, "failed · agent exited 1"),
        ({"status": "failed"}, "failed"),
        (
            {"status": "running", "is_current": True, "attention": "your_turn", "turns": 3},
            "your turn · 3 turns",
        ),
        (
            {"status": "running", "is_current": True, "attention": "your_turn", "round": 2},
            "round 2 · your turn",
        ),
        ({"status": "running", "is_current": True, "attention": "answering"}, "agent answering"),
        ({"status": "running", "is_current": True, "attention": "queued"}, "agent answering"),
        ({"status": "running", "is_current": True}, "running"),
        ({"status": "running"}, "running"),
        ({"status": "planned", "follows_current": True}, "next"),
        (
            {"status": "planned", "previous_is_gate": True, "previous_id": "gate"},
            "starts after the gate passes",
        ),
        ({"status": "planned", "previous_id": "tech"}, "starts after tech"),
        (
            {
                "status": "planned",
                "follows_current": True,
                "kind": "automatic",
                "previous_id": "tech",
            },
            "starts after tech",
        ),
        ({"status": "planned"}, ""),
    ],
)
def test_strip_line(overrides: dict[str, Any], expected: str) -> None:
    assert strip(**overrides) == expected


def track(**overrides: Any) -> str:
    values: dict[str, Any] = {
        "type": "interactive",
        "number": 1,
        "current": 1,
        "initiative_status": "running",
        "attention": None,
        "step": "ux",
        "k": 3,
        "j": 6,
        "run": a_run(),
        "run_label": "",
        "run_progress": None,
        "pr_merged_at": None,
        "previous": None,
    }
    values.update(overrides)
    return workflow_line(TrackFact(**values))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"run": None, "previous": "spec"}, "starts by itself when spec is done"),
        ({"run": None}, ""),
        ({"initiative_status": "cancelled"}, "cancelled"),
        ({"attention": "your_turn"}, "step 3 of 6 · ux · your turn"),
        ({"attention": "answering"}, "step 3 of 6 · ux · agent answering"),
        ({"attention": "queued"}, "step 3 of 6 · ux · agent answering"),
        ({"initiative_status": "waiting for her"}, "step 3 of 6 · ux · needs you"),
        ({"initiative_status": "failed"}, "step 3 of 6 · ux · failed"),
        ({}, "step 3 of 6 · ux · running"),
        (
            {"number": 1, "current": 2, "initiative_status": "running"},
            "completed 2026-11-03 · 6/6 steps",
        ),
        ({"initiative_status": "done"}, "completed 2026-11-03 · 6/6 steps"),
    ],
)
def test_interactive_workflow_line(overrides: dict[str, Any], expected: str) -> None:
    run = a_run(updated_at=datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
    overrides.setdefault("run", run)
    assert track(**overrides) == expected


def test_a_completed_interactive_run_without_updated_at_reads_created_at() -> None:
    run = a_run(updated_at=None, created_at=datetime(2026, 11, 2, 8, 0, tzinfo=UTC))

    assert track(run=run, current=2) == "completed 2026-11-02 · 6/6 steps"


def auto(**overrides: Any) -> str:
    base: dict[str, Any] = {"type": "auto", "number": 2, "current": 2}
    base.update(overrides)
    return track(**base)


def test_an_auto_run_done_and_merged() -> None:
    run = a_run(status="done")

    assert auto(run=run, pr_merged_at=ENDED) == "completed 2026-11-24"


def test_an_auto_run_done_with_a_pull_request_not_merged() -> None:
    run = a_run(status="done", compare_urls=("https://x/pull/1", "https://x/pull/2"))

    assert auto(run=run) == "Run done · pull request https://x/pull/1, https://x/pull/2 not merged"


def test_an_auto_run_done_without_a_link() -> None:
    assert auto(run=a_run(status="done")) == "Run done"


def test_an_auto_run_running_reads_label_progress_spend_and_budget() -> None:
    run = a_run(status="running", spend_usd=Decimal("1.5"), budget_usd=Decimal("20"))
    progress = Progress(1, 3, 2, 9, 4)

    line = auto(run=run, run_label="story 3 · agent", run_progress=progress)

    assert line == "story 3 · agent · 1/3 epics · 2/9 stories · 4 links · $1.50 / $20.00"


def test_an_auto_run_running_without_label_or_budget() -> None:
    run = a_run(status="running", spend_usd=Decimal("0"))

    assert auto(run=run, run_label="") == "t · $0.00"
