"""`application/rules/frames.py` — the frame arithmetic the two skip signals are stated in.

Every path here is one the shipped Templates really produce (`test_plan_shipped.py`), so
the hyphen in `commit-guard` and the two nesting depths are exercised rather than assumed.
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules.frames import (
    epic_frame,
    in_frame,
    rows_after,
    rows_in_frame,
    run_is_one_epic,
    story_frame,
    story_frames_after,
)
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    PAIR_PLAN,
    build_rows,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("stories[0].build", "stories[0]"),
        ("stories[1].commit-guard", "stories[1]"),
        ("epics[1].stories[3].verify", "epics[1].stories[3]"),
        ("epics[0].push", None),
        ("plan", None),
        ("stories[10].build", "stories[10]"),
    ],
)
def test_the_story_frame_is_the_innermost_stories_prefix(path: str, expected: str | None) -> None:
    assert story_frame(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("epics[1].stories[3].verify", "epics[1]"),
        ("epics[0].push", "epics[0]"),
        ("stories[0].build", None),
        ("plan", None),
    ],
)
def test_the_epic_frame_is_the_epics_prefix_whatever_is_nested_under_it(
    path: str, expected: str | None
) -> None:
    assert epic_frame(path) == expected


def test_a_segment_that_is_not_a_loop_index_is_not_a_frame() -> None:
    """`stories` without an index is a step id, not the `stories[n]` a skip acts on."""
    assert story_frame("stories.build") is None


def test_a_frame_contains_itself_and_what_is_nested_under_it() -> None:
    assert in_frame("stories[1]", "stories[1]")
    assert in_frame("stories[1].build", "stories[1]")


def test_a_frame_does_not_contain_a_longer_index_that_merely_starts_the_same() -> None:
    """A `startswith` on the bare prefix would put `stories[10]` inside `stories[1]`."""
    assert not in_frame("stories[10].build", "stories[1]")


def test_the_rows_of_a_frame_come_back_in_seq_order() -> None:
    rows = build_rows(new_id(), EPIC_PLAN)

    inside = rows_in_frame(rows, "stories[1]")

    assert [row.path for row in inside] == [
        "stories[1].sync",
        "stories[1].build",
        "stories[1].verify",
        "stories[1].commit-guard",
        "stories[1].after",
    ]


def test_rows_after_is_every_higher_seq_in_order() -> None:
    rows = build_rows(new_id(), EPIC_PLAN)

    assert [row.path for row in rows_after(rows, 12)] == ["push", "link"]


def test_the_last_row_has_nothing_after_it() -> None:
    rows = build_rows(new_id(), EPIC_PLAN)

    assert rows_after(rows, len(EPIC_PLAN)) == []


def test_the_later_story_frames_of_a_run_with_no_epic_loop_are_the_later_stories() -> None:
    rows = build_rows(new_id(), EPIC_PLAN)

    assert story_frames_after(rows, "stories[0]") == ["stories[1]"]


def test_the_last_story_frame_has_no_frame_after_it() -> None:
    rows = build_rows(new_id(), EPIC_PLAN)

    assert story_frames_after(rows, "stories[1]") == []


def test_later_story_frames_stop_at_the_epic_the_frame_belongs_to() -> None:
    """`skip_epic` skips the rest of *this* epic; the next epic's Stories are not its business."""
    rows = build_rows(new_id(), INITIATIVE_PLAN)

    assert story_frames_after(rows, "epics[0].stories[0]") == ["epics[0].stories[1]"]


def test_an_earlier_story_frame_of_the_same_epic_is_not_after_it() -> None:
    rows = build_rows(new_id(), INITIATIVE_PLAN)

    assert story_frames_after(rows, "epics[0].stories[1]") == []


# ── `run_is_one_epic`: the plan says it, not the Template's name ───────────────────────────
# Operator decision 2026-09-30: no template name hardcoded in product code. AD-13 admits
# `skip_epic` on a Run that is itself one epic, which has no `epics[i]` frame at all — this
# replaces the `EPIC_TEMPLATE == "epic"` assertion, and asserts the *shape* the rule is
# really about across all three plan shapes instead of one name.


def test_a_plan_that_loops_over_stories_and_nothing_above_them_is_one_epic() -> None:
    assert run_is_one_epic(build_rows(new_id(), EPIC_PLAN)) is True


def test_a_plan_with_an_epic_loop_is_not_one_epic() -> None:
    """Several epics: `skip_epic` has the parked row's own `epics[n]` frame to act on."""
    assert run_is_one_epic(build_rows(new_id(), INITIATIVE_PLAN)) is False


def test_a_plan_with_no_loop_at_all_is_not_one_epic() -> None:
    """An initialisation Run is no epic, so there is nothing for `skip_epic` to skip."""
    assert run_is_one_epic(build_rows(new_id(), PAIR_PLAN)) is False


def test_no_rows_at_all_is_not_one_epic() -> None:
    assert run_is_one_epic([]) is False
