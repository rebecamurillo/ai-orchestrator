"""A senior decision file whose frontmatter PyYAML cannot construct reads as no decision, so
the consult fails closed (story 4, AD-26, D13; `rules/consult.py::parse`)."""

from __future__ import annotations

from orchestrator.application.rules import consult


def test_a_decision_with_an_unconstructible_scalar_reads_as_no_decision() -> None:
    text = "---\nstatus: answer\nx: !!bool maybe\n---\nthe answer\n"

    assert consult.parse(text) is None


def test_the_same_decision_without_the_bad_scalar_reads() -> None:
    parsed = consult.parse("---\nstatus: answer\n---\nthe answer\n")

    assert parsed is not None
    assert parsed.status == "answer"
