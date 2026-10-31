"""A Story with two `git.commit` rows is one Story cell and one count (Operator-reported fix,
2026-10-30): the cells and `progress` are per Story frame, not per commit row, and a Story is
done only when every one of its commit rows has settled."""

from __future__ import annotations

from orchestrator.application.use_cases.run_views_summary import progress, story_cells
from tests.unit.application.writer_fixtures import build_rows, build_run

PLAN: tuple[tuple[str, str], ...] = (
    ("epics[0].stories[0].plan", "agent"),
    ("epics[0].stories[0].commit-a", "git.commit"),
    ("epics[0].stories[0].review", "agent"),
    ("epics[0].stories[0].commit-b", "git.commit"),
    ("epics[0].stories[1].plan", "agent"),
    ("epics[0].stories[1].commit-a", "git.commit"),
    ("epics[0].stories[1].review", "agent"),
    ("epics[0].stories[1].commit-b", "git.commit"),
    ("epics[0].push", "git.push"),
)


def _rows(statuses: dict[str, str]):
    run = build_run("running")
    return run, build_rows(run.id, PLAN, statuses)  # type: ignore[arg-type]


def test_a_story_with_two_commit_rows_is_one_cell() -> None:
    run, rows = _rows({})

    cells = story_cells(run, rows, {})

    assert [cell.story_id for cell in cells] == ["1", "2"]


def test_a_story_is_done_only_when_every_commit_row_settled() -> None:
    run, rows = _rows(
        {
            "epics[0].stories[0].commit-a": "done",
            "epics[0].stories[0].commit-b": "planned",
            "epics[0].stories[1].commit-a": "done",
            "epics[0].stories[1].commit-b": "done",
        }
    )

    cells = story_cells(run, rows, {})
    counted = progress(run, rows)

    assert [cell.state for cell in cells] == ["future", "done"]
    assert counted is not None
    assert (counted.stories_done, counted.stories_total) == (1, 2)


def test_a_story_with_every_commit_row_skipped_reads_skipped() -> None:
    run, rows = _rows(
        {
            "epics[0].stories[0].commit-a": "skipped",
            "epics[0].stories[0].commit-b": "skipped",
        }
    )

    assert next(cell.state for cell in story_cells(run, rows, {})) == "skipped"
