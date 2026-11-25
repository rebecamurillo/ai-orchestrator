"""The step line and progress line of an initiative row (story 4, epic 7; EXPERIENCE I1)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.rules.initiative_lines import progress_line, step_line
from orchestrator.application.rules.initiative_status import StatusReading
from orchestrator.application.use_cases.run_view_types import Progress
from tests.unit.initiative_fixtures import a_run, an_initiative

MERGED = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


def line(status: str, *, attention=None, reason="", step="intake", **facts) -> str:  # type: ignore[no-untyped-def]
    initiative = facts.pop("initiative", None) or an_initiative()
    return step_line(
        initiative,
        StatusReading(status, step, reason),  # type: ignore[arg-type]
        attention,
        ended_turns=facts.pop("turns", 0),
        current_label=facts.pop("label", ""),
        harness=facts.pop("harness", None),
    )


def test_a_cancelled_initiative_says_its_branch_is_deleted() -> None:
    assert line("cancelled") == "spec branch deleted · slug free"


def test_a_cancelled_initiative_whose_cleanup_failed_says_why() -> None:
    initiative = an_initiative(branch_cleanup_error="remote refused")

    assert (
        line("cancelled", initiative=initiative)
        == "cancelled · branch cleanup failed: remote refused"
    )


def test_a_done_initiative_names_the_merge_date() -> None:
    initiative = an_initiative(pr_merged_at=MERGED)

    assert line("done", initiative=initiative) == "build done · pull request merged 2026-11-03"


def test_her_turn_counts_the_ended_turns() -> None:
    assert line("running", attention="your_turn", turns=14) == "your turn · conversation, 14 turns"


@pytest.mark.parametrize("attention", ["answering", "queued"])
def test_an_agent_at_work_reads_answering(attention: str) -> None:
    assert line("running", attention=attention) == "agent answering"


def test_waiting_for_her_names_the_reason_or_the_step() -> None:
    assert line("waiting for her", reason="two open questions") == "needs you · two open questions"
    assert line("waiting for her", step="gate") == "needs you · gate"


def test_a_failure_names_its_reason_when_it_has_one() -> None:
    assert line("failed", reason="Run cancelled") == "failed · Run cancelled"
    assert line("failed") == "failed"


def test_a_running_initiative_with_a_reason_shows_the_reason() -> None:
    assert line("running", reason="waiting for a slot") == "waiting for a slot"


def test_otherwise_the_label_and_the_harness_join_and_empty_parts_drop() -> None:
    assert line("running", label="Plan epics", harness="claude") == "Plan epics · claude"
    assert line("running", step="build") == "build"
    assert line("running", step="", harness="codex") == "codex"


def test_an_interactive_workflow_counts_its_steps() -> None:
    assert progress_line("interactive", k=2, j=3, run=None, run_progress=None) == "step 2 of 3"


def test_an_auto_workflow_without_a_run_has_no_progress() -> None:
    assert progress_line("auto", k=1, j=1, run=None, run_progress=None) == ""


def test_an_auto_workflow_without_counts_shows_the_template_and_spend() -> None:
    run = a_run(spend_usd=Decimal("2.5"), template_name="p/build")

    assert progress_line("auto", k=1, j=1, run=run, run_progress=None) == "p/build · $2.50"


@pytest.mark.parametrize(
    ("links", "noun"),
    [(1, "1 link"), (3, "3 links")],
)
def test_an_auto_workflow_shows_epics_stories_and_links(links: int, noun: str) -> None:
    run = a_run(spend_usd=Decimal("8.1"))
    counts = Progress(epics_done=1, epics_total=2, stories_done=3, stories_total=5, links=links)
    flat = Progress(epics_done=None, epics_total=None, stories_done=0, stories_total=2, links=0)

    assert progress_line("auto", k=1, j=1, run=run, run_progress=counts) == (
        f"1/2 epics · 3/5 stories · {noun} · $8.10"
    )
    assert progress_line("auto", k=1, j=1, run=run, run_progress=flat) == (
        "0/2 stories · 0 links · $8.10"
    )
