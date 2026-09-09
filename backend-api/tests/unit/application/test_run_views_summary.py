"""`summary.skipped` after a `skip_story` (6.4, FR-11, FR-20, SM-C3).

`skip_epic` marks a whole later frame `skipped`, its `git.commit` row included, so the
commit-guard row's own status was enough while that was the only way a Story got skipped.
`skip_story` is the opposite by design: the frame's commit-guard still runs — under the
message `story {id}: skipped by operator` — so the leftovers land on the branch before the
next Story starts, and that row reaches `done`. The list therefore reads the *frame*, and it
reads the reason as well as the status, so the two `skipped` rows a Run leaves for other
reasons (`no quality_gate_command`, and an already-done Story's own four) stay out of it.

The Board card's `m/m` is asserted here too, unnarrowed: FR-20's `[ASSUMPTION]` counts a
skipped Story toward `stories_done` so the epic reads complete, and names it beside the
compare link instead.
"""

from __future__ import annotations

from orchestrator.application.use_cases.run_views_summary import (
    progress,
    skipped_stories,
    story_cells,
    summary,
)
from orchestrator.application.use_cases.signal_effects import SKIPPED_BY_OPERATOR
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.application.writer_fixtures import EPIC_PLAN, build_rows, build_run

SKIPPED = "skipped"


def a_done_run(**over: object):
    return build_run("done", **over)


def rows_with(run_id, statuses: dict[str, str], reasons: dict[str, str] | None = None):
    """The `epic@1` plan with the named rows moved, and reasons where a test needs them."""
    given = reasons or {}
    return [
        row.model_copy(
            update={
                "status": statuses.get(row.path, row.status),
                "reason": given.get(row.path),
            }
        )
        for row in build_rows(run_id, EPIC_PLAN)
    ]


def an_operator_skipped_second_story(run_id) -> list[StepRun]:
    """`stories[1]` as `skip_story` leaves it: agent and checkpoint rows skipped by the
    Operator, verify re-baselined green, commit-guard committed under the skip message."""
    return rows_with(
        run_id,
        {
            "stories[0].commit-guard": "done",
            "stories[1].build": SKIPPED,
            "stories[1].verify": "done",
            "stories[1].commit-guard": "done",
            "stories[1].after": SKIPPED,
        },
        {"stories[1].build": SKIPPED_BY_OPERATOR, "stories[1].after": SKIPPED_BY_OPERATOR},
    )


def test_a_story_the_operator_skipped_is_listed_although_its_commit_ran() -> None:
    run = a_done_run()
    rows = an_operator_skipped_second_story(run.id)

    view = summary(run, rows)

    assert view is not None
    assert view.skipped == ["2"]


def test_the_epic_still_reads_complete_on_the_card() -> None:
    """FR-20's `[ASSUMPTION]`: a skipped Story counts toward `stories_done`, so the Run's
    own progress is `2/2` and the skip is named beside the link rather than in the count."""
    run = a_done_run()
    rows = an_operator_skipped_second_story(run.id)

    counted = progress(run, rows)

    assert counted is not None
    assert (counted.stories_done, counted.stories_total) == (2, 2)


def test_a_skipped_commit_guard_row_is_still_listed_on_its_own() -> None:
    """The older path — a frame nothing ran at all — keeps answering exactly as it did."""
    run = a_done_run()
    rows = rows_with(run.id, {"stories[1].commit-guard": SKIPPED})

    assert skipped_stories(rows) == ["2"]


def test_a_verify_planned_away_for_want_of_a_quality_gate_is_not_a_skipped_story() -> None:
    rows = rows_with(
        build_run().id,
        {"stories[0].verify": SKIPPED},
        {"stories[0].verify": "no quality_gate_command"},
    )

    assert skipped_stories(rows) == []


def test_rows_skipped_without_the_operators_reason_are_not_a_skipped_story() -> None:
    """An already-done Story ends in consecutive `skipped` rows (`apply_step_result`'s own
    successor rule) and must not read as one the Operator gave up on."""
    rows = rows_with(build_run().id, {"stories[0].build": SKIPPED, "stories[0].verify": SKIPPED})

    assert skipped_stories(rows) == []


def test_a_run_that_is_not_done_has_no_summary_at_all() -> None:
    run = build_run("needs_you")

    assert summary(run, an_operator_skipped_second_story(run.id)) is None


def test_the_story_cell_of_a_skipped_story_still_reads_done() -> None:
    """The strip is deliberately not narrowed with the list: its own per-epic `n/m` counts
    `done` cells, and a cell reading `skipped` here would disagree with the card's `2/2`."""
    run = a_done_run()
    rows = an_operator_skipped_second_story(run.id)

    cells = story_cells(run, rows, {})

    assert [(cell.story_id, cell.state) for cell in cells] == [("1", "done"), ("2", "done")]
