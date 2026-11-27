"""`story_file.body`: the text after the closing frontmatter fence (epic 8 story 2)."""

from __future__ import annotations

from orchestrator.application import story_file


def test_the_body_is_what_follows_the_closing_fence() -> None:
    assert story_file.body("---\nstatus: fail\n---\n\n- one\n- two\n") == "\n- one\n- two"


def test_there_is_no_body_without_frontmatter() -> None:
    assert story_file.body("# just a heading\n") is None


def test_trailing_blank_lines_inside_the_frontmatter_do_not_shift_it() -> None:
    assert story_file.body("---\nstatus: pass\n\n\n---\nbody\n") == "body"
