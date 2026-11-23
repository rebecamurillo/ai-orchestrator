"""`rules/session`'s step scope: the skill reference and the scopes at a conversation row
(epic 4 story 4, AC4, AC5)."""

from __future__ import annotations

import pytest

from orchestrator.application.rules import session
from tests.unit.application.writer_fixtures import build_rows, build_run

LISTED = frozenset({"bmad-prd"})


@pytest.mark.parametrize(
    ("skill", "installed", "expected"),
    [
        (None, None, "senior-session"),
        ("  ", LISTED, "senior-session"),
        ("skills/tech-lead/SKILL.md", LISTED, "skills/tech-lead/SKILL.md"),
        ("bmad-prd", None, "bmad-prd"),
        ("bmad-prd", LISTED, "bmad-prd"),
        ("bmad-prd", frozenset({"senior-session"}), None),
    ],
)
def test_step_skill_ref(
    skill: str | None, installed: frozenset[str] | None, expected: str | None
) -> None:
    assert session.step_skill_ref(skill, installed) == expected


def test_opening_line_without_a_skill_is_unchanged() -> None:
    assert session.opening_line(("story", None), "hi") == "senior-session story -\nhi"


def test_opening_line_names_the_skill_it_is_given() -> None:
    assert session.opening_line(("a",), "hi", skill="bmad-prd") == "bmad-prd a\nhi"


def test_a_conversation_row_has_the_step_scope_only() -> None:
    rows = build_rows(build_run().id, (("intake", "conversation"),))

    assert session.scopes_at("intake", rows) == ("step",)


def test_a_story_row_keeps_its_scopes() -> None:
    rows = build_rows(build_run().id, (("stories[0].build", "agent"),))

    assert session.scopes_at("stories[0].build", rows) == ("story", "epic", "run")


def test_no_park_path_has_no_scope() -> None:
    assert session.scopes_at(None, []) == ()
