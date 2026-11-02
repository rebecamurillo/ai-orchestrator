"""`ia-agents-skills/senior-consult/SKILL.md` at a failed verification (story 1-6,
SPEC-senior-unblock CAP-3, AD-22).

The same senior, the same decision file and the same hard rule, with a second kind of stop:
the repository's verify command failed after the Template's redispatches. The diagnosis is the
answer, the implementer receives it in a fresh session, and the stop's must-escalate cases are
unchanged."""

from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "senior-consult" / "SKILL.md"


def text() -> str:
    return SKILL.read_text()


def test_the_skill_names_the_failed_verification_as_a_second_stop() -> None:
    body = text()

    assert "## At a failed verification" in body
    assert "verify command" in body


def test_the_senior_reads_the_failure_the_log_and_the_diff() -> None:
    section = text().split("## At a failed verification", maxsplit=1)[1]

    assert "output tail" in section
    assert "session log" in section
    assert "git diff" in section


def test_the_answer_is_a_diagnosis_a_fresh_session_can_act_on() -> None:
    section = text().split("## At a failed verification", maxsplit=1)[1]

    assert "root cause" in section
    assert "fresh session" in section
    assert "status: answer" in section


def test_the_hard_rule_and_the_escalation_cases_still_hold_for_it() -> None:
    section = text().split("## At a failed verification", maxsplit=1)[1]

    assert "nothing but the decision file" in section
    assert "Escalate" in section
    assert "status: escalate" in section


def test_the_readme_names_the_second_stop() -> None:
    readme = (SKILL.parents[1] / "README.md").read_text()

    assert "verify_failed" in readme
