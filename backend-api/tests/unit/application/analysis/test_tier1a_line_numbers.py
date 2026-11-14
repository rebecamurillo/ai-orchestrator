"""`added_line_numbers`: the head line numbers a zero-context diff adds (epic 5 story 3)."""

from __future__ import annotations

from orchestrator.application.analysis.tier1a import added_line_numbers


def test_a_hunk_adds_the_numbers_from_its_new_start() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -3 +3,2 @@\n-old\n+new one\n+new two\n"
    )
    assert added_line_numbers(diff) == {"a.py": frozenset({3, 4})}


def test_several_hunks_and_files_each_keep_their_own_numbers() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,0 +2 @@\n+x\n"
        "@@ -9,2 +10,2 @@\n-a\n-b\n+c\n+d\n"
        "diff --git a/b.ts b/b.ts\n--- a/b.ts\n+++ b/b.ts\n@@ -5 +7 @@\n-q\n+r\n"
    )
    assert added_line_numbers(diff) == {
        "a.py": frozenset({2, 10, 11}),
        "b.ts": frozenset({7}),
    }


def test_an_added_line_that_starts_with_plus_plus_is_a_line_not_a_header() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -0,0 +1,2 @@\n+++ looks like a header\n+b\n"
    )
    assert added_line_numbers(diff) == {"a.py": frozenset({1, 2})}


def test_a_deleted_file_has_no_numbers() -> None:
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n"
    assert added_line_numbers(diff) == {}


def test_a_pure_deletion_and_a_no_newline_marker_add_nothing_and_do_not_shift_numbers() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -4 +3,0 @@\n-gone\n"
        "@@ -8 +7 @@\n-x\n\\ No newline at end of file\n+y\n\\ No newline at end of file\n"
    )
    assert added_line_numbers(diff) == {"a.py": frozenset({7})}


def test_context_lines_advance_the_head_number() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,3 @@\n keep\n+added\n keep2\n"
    )
    assert added_line_numbers(diff) == {"a.py": frozenset({2})}


def test_an_empty_diff_has_no_numbers() -> None:
    assert added_line_numbers("") == {}
