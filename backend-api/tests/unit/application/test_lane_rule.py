"""`rules/lane.py::lane_of` (epic 3 story 2, AC1): the lane a Run waits in."""

from __future__ import annotations

from orchestrator.application.rules.lane import lane_of


def test_an_interactive_template_with_a_conversation_row_is_interactive() -> None:
    assert lane_of("interactive", {"agent", "conversation"}) == "interactive"


def test_an_interactive_template_without_a_conversation_row_walks() -> None:
    assert lane_of("interactive", {"shell", "agent", "git.merge", "git.push"}) == "walk"


def test_an_auto_template_walks_even_with_a_conversation_row() -> None:
    assert lane_of("auto", {"conversation"}) == "walk"


def test_an_auto_template_with_no_rows_walks() -> None:
    assert lane_of("auto", set()) == "walk"
