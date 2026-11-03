"""`ia-agents-skills/senior-consult/SKILL.md` (story 1-4, SPEC-senior-unblock CAP-1, AD-22).

The senior is an architect reviewing the agent's concern, escalates every case the SPEC says
it must, writes one decision file in the format `rules/consult.py` reads, and changes
nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "senior-consult" / "SKILL.md"
README = SKILL.parents[1] / "README.md"

#: SPEC-senior-unblock's must-escalate list, one entry per case.
MUST_ESCALATE = (
    "anchor text would have to change",
    "the story's intent is ambiguous",
    "an irreversible or destructive action",
    "credentials or infrastructure outside the repository",
    "a product or design decision",
)


def text() -> str:
    return SKILL.read_text()


def test_the_skill_is_named_after_its_directory_and_takes_no_args() -> None:
    _, block, _ = text().split("---\n", 2)
    front = yaml.safe_load(block)

    assert front["name"] == "senior-consult"
    assert "args" not in front


def test_the_senior_is_the_architect_reviewing_the_concern() -> None:
    assert "review and validate the agent's concern against the story's intent" in text()


@pytest.mark.parametrize("case", MUST_ESCALATE)
def test_every_must_escalate_case_is_stated(case: str) -> None:
    assert case in text()


def test_the_decision_format_is_the_one_the_rule_reads() -> None:
    body = text()

    assert "`status`" in body
    assert "`reason`" in body
    for status in ("answer", "escalate"):
        assert f"status: {status}" in body
    assert "the body is the answer" in body


def test_the_senior_changes_nothing_but_the_decision_file() -> None:
    assert "change nothing but the decision file" in text()


def test_the_readme_lists_the_skill() -> None:
    assert "`senior-consult`" in README.read_text()
