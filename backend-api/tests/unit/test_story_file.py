"""`application/story_file.py`: the one reader of the file FR-16 routes on.

Everything the routing rule is allowed to know about a Story file is decided here, so every
shape the harness can leave behind is a case below: a file with no frontmatter, a fence that
never closes, YAML that does not load, a frontmatter with no `status`, a `## Auto Run Result`
section that is absent, that runs to the end of the file, or that is followed by another
heading. The two writers are here too — a redispatched attempt is handed back a file whose
frontmatter says `in-progress` and whose body carries the verify failure (FR-10).

Nothing here reads a file: `parse` takes the text, because `application/` reads the worktree
through the `Workspace` port and never through `pathlib` (AD-2).
"""

from __future__ import annotations

import pytest

from orchestrator.application.story_file import (
    AUTO_RUN_RESULT,
    NO_EXIT_CODE,
    STATUS_KEY,
    StoryFile,
    after_verify,
    appended,
    blocking_condition,
    parse,
    section,
    with_status,
)

#: The section FR-10 appends, as `route`'s own reader finds it again.
VERIFY_FAILURE_HEADING = "## Verify Failure"

PATH = "specs/notifications/stories/4-1-notify.md"

BLOCKED_FILE = """\
---
status: blocked
title: notify
---

# Story 4-1

## Auto Run Result

Status: blocked
Blocking condition: intent gap
Questions:
- which channel?

## Notes

not part of the section
"""

#: The section as `route` must see it: the heading, every line under it, nothing after.
BLOCKED_SECTION = """\
## Auto Run Result

Status: blocked
Blocking condition: intent gap
Questions:
- which channel?"""


def a_file(frontmatter: str, body: str = "") -> str:
    return f"---\n{frontmatter}\n---\n{body}"


# ── parse ────────────────────────────────────────────────────────────────────


def test_a_blocked_file_is_read_as_its_status_its_section_and_its_condition() -> None:
    parsed = parse(PATH, BLOCKED_FILE)

    assert parsed == StoryFile(
        path=PATH,
        status="blocked",
        auto_run_result=BLOCKED_SECTION,
        blocking_condition="intent gap",
    )


def test_a_done_file_carries_no_blocking_condition() -> None:
    parsed = parse(PATH, a_file("status: done", "# Story\n"))

    assert parsed is not None
    assert (parsed.status, parsed.blocking_condition, parsed.auto_run_result) == ("done", None, "")


def test_the_status_is_stripped_of_the_quoting_yaml_allows() -> None:
    parsed = parse(PATH, a_file("status: 'ready-for-dev'"))

    assert parsed is not None
    assert parsed.status == "ready-for-dev"


def test_a_file_with_no_frontmatter_at_all_is_unreadable() -> None:
    assert parse(PATH, "# Story 4-1\n\nno fence here\n") is None


def test_an_empty_file_is_unreadable() -> None:
    assert parse(PATH, "") is None


def test_a_fence_that_never_closes_is_unreadable() -> None:
    assert parse(PATH, "---\nstatus: done\n\n# Story\n") is None


def test_frontmatter_that_does_not_load_as_yaml_is_unreadable() -> None:
    """The YAML error is caught here; a broken file parks the Run, it never raises."""
    assert parse(PATH, a_file("status: [unclosed")) is None


def test_frontmatter_that_is_not_a_mapping_is_unreadable() -> None:
    assert parse(PATH, a_file("- one\n- two")) is None


def test_frontmatter_with_no_status_key_is_unreadable() -> None:
    assert parse(PATH, a_file("title: notify")) is None


def test_a_status_key_with_no_value_is_unreadable() -> None:
    assert parse(PATH, a_file(f"{STATUS_KEY}:")) is None


def test_a_status_that_is_not_text_is_unreadable() -> None:
    """`status: 3` is a file no route below knows; it is the same failure as no status."""
    assert parse(PATH, a_file("status: 3")) is None


def test_a_status_that_is_only_whitespace_is_unreadable() -> None:
    assert parse(PATH, a_file("status: '   '")) is None


# ── section ──────────────────────────────────────────────────────────────────


def test_a_missing_heading_is_an_empty_section_rather_than_a_refusal() -> None:
    assert section("# Story\n\nnothing here\n", AUTO_RUN_RESULT) == ""


def test_a_section_that_runs_to_the_end_of_the_file_is_taken_whole() -> None:
    text = f"# Story\n\n{AUTO_RUN_RESULT}\n\nStatus: blocked\n"

    assert section(text, AUTO_RUN_RESULT) == f"{AUTO_RUN_RESULT}\n\nStatus: blocked"


def test_a_deeper_heading_does_not_end_the_section() -> None:
    text = f"{AUTO_RUN_RESULT}\n\n### Evidence\n\n- a\n"

    assert section(text, AUTO_RUN_RESULT) == f"{AUTO_RUN_RESULT}\n\n### Evidence\n\n- a"


def test_the_next_second_level_heading_ends_the_section() -> None:
    assert section(BLOCKED_FILE, AUTO_RUN_RESULT) == BLOCKED_SECTION


# ── blocking_condition ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Blocking condition: no subagents", "no subagents"),
        ("  Blocking condition:   spaced  ", "spaced"),
        ("Blocking condition:", None),
        ("Blocking condition:    ", None),
        ("Status: blocked", None),
        ("", None),
    ],
)
def test_the_condition_is_the_rest_of_its_own_line(text: str, expected: str | None) -> None:
    assert blocking_condition(text) == expected


def test_the_first_condition_line_wins() -> None:
    assert blocking_condition("Blocking condition: one\nBlocking condition: two") == "one"


# ── with_status ──────────────────────────────────────────────────────────────


def test_the_status_line_is_replaced_and_the_rest_of_the_frontmatter_kept() -> None:
    rewritten = with_status(BLOCKED_FILE, "in-progress")

    assert rewritten.startswith("---\nstatus: in-progress\ntitle: notify\n---\n")
    assert "status: blocked" not in rewritten
    parsed = parse(PATH, rewritten)
    assert parsed is not None
    assert parsed.status == "in-progress"


def test_the_body_survives_the_rewrite_verbatim() -> None:
    rewritten = with_status(BLOCKED_FILE, "in-progress")

    assert section(rewritten, AUTO_RUN_RESULT) == BLOCKED_SECTION


def test_a_file_with_no_frontmatter_is_given_one() -> None:
    rewritten = with_status("# Story 4-1\n", "in-progress")

    parsed = parse(PATH, rewritten)
    assert parsed is not None
    assert parsed.status == "in-progress"
    assert "# Story 4-1" in rewritten


def test_frontmatter_with_no_status_line_gains_one() -> None:
    rewritten = with_status(a_file("title: notify", "# Story\n"), "in-progress")

    parsed = parse(PATH, rewritten)
    assert parsed is not None
    assert parsed.status == "in-progress"
    assert "title: notify" in rewritten


# ── appended ─────────────────────────────────────────────────────────────────


def test_a_block_is_appended_after_a_blank_line_and_ends_with_a_newline() -> None:
    assert appended("# Story\n", "## Verify Failure\n\nCommand: make test") == (
        "# Story\n\n## Verify Failure\n\nCommand: make test\n"
    )


def test_a_text_that_did_not_end_in_a_newline_still_separates_the_block() -> None:
    assert appended("# Story", "## Verify Failure") == "# Story\n\n## Verify Failure\n"


def test_appending_to_nothing_writes_the_block_alone() -> None:
    assert appended("", "## Verify Failure") == "## Verify Failure\n"


# ── after_verify ─────────────────────────────────────────────────────────────


def test_the_verify_failure_names_the_command_the_code_and_the_log_tail() -> None:
    written = after_verify(BLOCKED_FILE, "make test", 1, ["FAILED a", "1 failed"])

    assert section(written, VERIFY_FAILURE_HEADING) == (
        "## Verify Failure\n\nCommand: make test\nExit code: 1\n\nFAILED a\n1 failed"
    )


def test_the_frontmatter_goes_back_to_in_progress() -> None:
    parsed = parse(PATH, after_verify(BLOCKED_FILE, "make test", 1, []))

    assert parsed is not None
    assert parsed.status == "in-progress"


def test_an_exit_code_the_verify_row_never_recorded_is_stated_not_repred() -> None:
    """A `verify` row sent back before any attempt recorded a code has none to show, and
    `None` is a Python repr in a document a coding agent reads (PRD NFR-8)."""
    written = after_verify(BLOCKED_FILE, "make test", None, [])

    assert "Exit code: not recorded" in written
    assert "Exit code: None" not in written
    assert NO_EXIT_CODE == "not recorded"
