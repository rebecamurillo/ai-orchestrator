"""`ia-agents-skills/senior-consult/SKILL.md` reviewing a protected-path diff (story 1-8, hard
rule 1 as amended 2026-11-02, AD-17).

At a `protected_path` stop the senior reads the diff and the story baseline beside its
decision file, and accepts only when the story requires every hunk, naming every listed path
with a reason; otherwise, or when unsure, it escalates."""

from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "senior-consult" / "SKILL.md"
HEADING = "## Reviewing a protected-path diff"


def section() -> str:
    body = SKILL.read_text()
    assert HEADING in body
    after = body.split(HEADING, maxsplit=1)[1]
    return after.split("\n## ", maxsplit=1)[0]


def test_the_stop_is_named_by_its_condition() -> None:
    assert "When the condition starts with `protected path modified:`" in section()


def test_the_senior_reads_the_diff_and_the_story_baseline_beside_the_decision_file() -> None:
    text = section()

    assert "Read the `.diff` file beside your decision file" in text
    assert "`### {path}`" in text
    assert "the `.story.md` baseline" in text


def test_an_accept_names_every_listed_path_with_a_reason() -> None:
    text = section()

    assert "status: accept" in text
    assert "approved_files: [" in text
    assert "names every listed path" in text
    assert "fewer or more files fails the consult" in text
    assert "no `reason` fails the consult" in text


def test_an_accept_requires_the_story_to_require_each_hunk() -> None:
    text = section()

    assert '"required", as "Approving test edits" defines it' in text
    assert "each hunk of each\nlisted file" in text


def test_otherwise_or_when_unsure_the_senior_escalates() -> None:
    assert "Otherwise, or when unsure, escalate" in section()


def test_the_description_names_the_protected_path_stop() -> None:
    head = SKILL.read_text().split("---", maxsplit=2)[1]

    assert "a protected-path stop" in head
