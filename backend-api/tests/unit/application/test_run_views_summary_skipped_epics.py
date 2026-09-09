"""`summary.skipped_epics` after a `skip_epic` on a rejected push (6.5, FR-20).

`test_run_views_summary.py` (6.4) proves `summary.skipped` for `skip_story`; this is its
epic-numbered sibling. `skip_epic` on `push_rejected` is the only path that ever leaves a
`push` row `skipped` under `SKIPPED_BY_OPERATOR` (`signal_effects.py::_skip_remote_rows`),
so that is the one fact this module reads back.
"""

from __future__ import annotations

from orchestrator.application.use_cases.run_views_summary import skipped_epics, summary
from orchestrator.application.use_cases.signal_effects import SKIPPED_BY_OPERATOR
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.application.writer_fixtures import EPIC_PLAN, INITIATIVE_PLAN, build_rows, build_run

SKIPPED = "skipped"


def a_done_run(**over: object):
    return build_run("done", **over)


def rows_with(
    run_id,
    plan: tuple[tuple[str, str], ...],
    statuses: dict[str, str],
    reasons: dict[str, str] | None = None,
) -> list[StepRun]:
    given = reasons or {}
    return [
        row.model_copy(
            update={
                "status": statuses.get(row.path, row.status),
                "reason": given.get(row.path),
            }
        )
        for row in build_rows(run_id, plan)
    ]


def test_a_rejected_pushs_epic_is_numbered_one_based_off_its_own_bracket() -> None:
    run = a_done_run()
    rows = rows_with(
        run.id,
        INITIATIVE_PLAN,
        {"epics[0].push": SKIPPED, "epics[0].link": SKIPPED},
        {"epics[0].push": SKIPPED_BY_OPERATOR, "epics[0].link": SKIPPED_BY_OPERATOR},
    )

    assert skipped_epics(rows) == [1]


def test_the_second_epics_rejected_push_is_numbered_two() -> None:
    run = a_done_run()
    rows = rows_with(
        run.id,
        INITIATIVE_PLAN,
        {"epics[1].push": SKIPPED},
        {"epics[1].push": SKIPPED_BY_OPERATOR},
    )

    assert skipped_epics(rows) == [2]


def test_an_epic_whose_push_ran_is_not_listed() -> None:
    run = a_done_run()
    rows = build_rows(run.id, INITIATIVE_PLAN, {"epics[0].push": "done", "epics[1].push": "done"})

    assert skipped_epics(rows) == []


def test_a_push_skipped_for_a_reason_other_than_the_operator_is_not_listed() -> None:
    """A cancelled Run marks every unstarted row `skipped` under the same reason
    (`signal_effects.py::_cancel`), but `summary` only ever calls this for a `done` Run, and
    a genuinely different reason must not read as an Operator's own skip either."""
    run = a_done_run()
    rows = rows_with(
        run.id, INITIATIVE_PLAN, {"epics[0].push": SKIPPED}, {"epics[0].push": "some other reason"}
    )

    assert skipped_epics(rows) == []


def test_a_plain_epic_templates_own_push_row_has_no_bracket_to_number() -> None:
    """`epic@1`'s own `push` row carries no `epics[n]` frame at all (`epic_frame` answers
    `None`) — `skip_epic` still skips it (`_skip_remote_rows`), this list just cannot number
    it, the same way `progress()` already treats that Template's own epic count as `None`."""
    run = a_done_run()
    rows = rows_with(run.id, EPIC_PLAN, {"push": SKIPPED}, {"push": SKIPPED_BY_OPERATOR})

    assert skipped_epics(rows) == []


def test_both_epics_of_an_initiative_skipped_in_turn_are_both_listed_in_order() -> None:
    """Reachable over two signals, not one: `epics[0]`'s own `push_rejected` skip queues
    `epics[1].checkout`, and a second `push_rejected` on `epics[1]`'s own push can skip that
    one too — the list accumulates rather than only ever holding one entry."""
    run = a_done_run()
    rows = rows_with(
        run.id,
        INITIATIVE_PLAN,
        {"epics[0].push": SKIPPED, "epics[0].link": SKIPPED, "epics[1].push": SKIPPED},
        {
            "epics[0].push": SKIPPED_BY_OPERATOR,
            "epics[0].link": SKIPPED_BY_OPERATOR,
            "epics[1].push": SKIPPED_BY_OPERATOR,
        },
    )

    assert skipped_epics(rows) == [1, 2]


def test_the_done_summary_carries_skipped_epics_beside_skipped_stories() -> None:
    run = a_done_run()
    rows = rows_with(
        run.id,
        INITIATIVE_PLAN,
        {"epics[0].push": SKIPPED, "epics[0].link": SKIPPED},
        {"epics[0].push": SKIPPED_BY_OPERATOR, "epics[0].link": SKIPPED_BY_OPERATOR},
    )

    view = summary(run, rows)

    assert view is not None
    assert view.skipped_epics == [1]
