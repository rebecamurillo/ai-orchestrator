"""`ia-agents-skills/senior-consult/SKILL.md` approving test edits (story 1-5, hard rule 1 as
amended 2026-11-02, AD-17).

At a `blocked` stop the senior may name existing test files the story requires changing, in
the answer's frontmatter. "Required" is judged against the anchors and the story baseline,
never the live story file the agent can write; anchors are never named; everything else
escalates."""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "senior-consult" / "SKILL.md"
HEADING = "## Approving test edits"


def section() -> str:
    body = SKILL.read_text()
    assert HEADING in body
    after = body.split(HEADING, maxsplit=1)[1]
    return after.split("\n## ", maxsplit=1)[0]


def test_an_answer_may_name_approved_files_in_its_frontmatter() -> None:
    text = section()

    assert "approved_files: [" in text
    assert "status: answer" in text
    assert "only for existing test files that the story requires changing" in text


def test_required_means_the_anchors_or_the_story_baseline_state_the_new_behaviour() -> None:
    text = section()

    for source in ("`SPEC.md`", "`stories.yaml`", "`.story.md`"):
        assert source in text
    assert "acceptance criteria" in text
    assert "`## Do not touch`" in text


def test_the_revision_must_be_the_rule_1b_revision() -> None:
    text = section()

    assert "only the assertions that pinned the old behaviour" in text
    assert "as thoroughly" in text
    assert "names the story and the date" in text


def test_a_declaration_only_the_live_story_file_carries_is_escalated() -> None:
    text = section()

    assert "only the live story file" in text
    assert "the agent's own claim" in text


def test_hub_paths_and_anchors() -> None:
    text = section()

    assert "`{workdir}/…`" in text
    assert "Never name an anchor" in text


@pytest.mark.parametrize(
    "case", ["a deletion", "a skip", "a relaxed assertion", "an unrelated test", "anything unsure"]
)
def test_these_cases_are_escalated(case: str) -> None:
    assert case in section()


def test_the_body_names_the_files_too() -> None:
    assert "Name the files in the answer body too" in section()
