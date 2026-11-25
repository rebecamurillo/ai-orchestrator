"""The unmerged paths of a `merge_conflict` stop (story 6, epic 7; AC4)."""

from __future__ import annotations

from orchestrator.application.rules import merge_conflicts
from orchestrator.infrastructure.git import worktrees


def test_the_listing_after_the_heading_is_parsed_in_order() -> None:
    output = "merge failed\nconflicted paths:\ninitiatives/snake/PRD.md\nREADME.md"

    assert merge_conflicts.conflict_files(output) == ["initiatives/snake/PRD.md", "README.md"]


def test_blank_lines_are_dropped() -> None:
    assert merge_conflicts.conflict_files("x\nconflicted paths:\n\na.md\n\n  \nb.md\n") == [
        "a.md",
        "b.md",
    ]


def test_the_last_heading_wins() -> None:
    output = "conflicted paths:\nold.md\nagain\nconflicted paths:\nnew.md"

    assert merge_conflicts.conflict_files(output) == ["new.md"]


def test_no_heading_and_no_output_list_nothing() -> None:
    assert merge_conflicts.conflict_files("merge failed") == []
    assert merge_conflicts.conflict_files(None) == []


def test_the_heading_has_one_definition() -> None:
    assert worktrees.CONFLICTED_HEADING is merge_conflicts.CONFLICTED_HEADING
