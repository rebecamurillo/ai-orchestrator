"""`rules/merge_conflict.py`: the unmerged paths of a porcelain status (story 8.4)."""

from __future__ import annotations

import pytest

from orchestrator.application.rules.merge_conflict import unmerged_paths


def test_unmerged_paths_keeps_conflicts_and_drops_untracked_and_staged() -> None:
    status = "UU a.md\nAA b.md\n?? c.md\nM  d.md\n"

    assert unmerged_paths(status) == ("a.md", "b.md")


def test_a_clean_status_has_no_unmerged_path() -> None:
    assert unmerged_paths("") == ()


@pytest.mark.parametrize("code", ["DD", "AU", "UD", "UA", "DU", "AA", "UU"])
def test_every_unmerged_code_counts(code: str) -> None:
    assert unmerged_paths(f"{code} dir/f.txt") == ("dir/f.txt",)


@pytest.mark.parametrize("line", [" M a", "A  a", "MM a", "?? a", "D  a", " D a"])
def test_modified_added_and_untracked_lines_are_not_unmerged(line: str) -> None:
    assert unmerged_paths(line) == ()
