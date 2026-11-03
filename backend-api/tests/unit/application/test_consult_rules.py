"""`rules/consult.py` (story 1-4, spine AD-22, ratified 2026-11-01): the decision file is read
here and nowhere else, never from model output; which stop is offered; which record delivers
the senior's answer."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.rules import consult
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from tests.unit.fakes.clock import EPOCH

PATH = "stories[0].implement"
PLANNED = {
    "model": "senior",
    "harness": "",
    "skill": "senior-consult",
    "on": ["blocked"],
    "timeout_min": None,
    "prompts": {"dispatch": "d", "answer": 'Senior on "{condition}": {answer}'},
}


def a_row(consults: dict[str, Any] | None = None, **resolved: Any) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=5,
        path=PATH,
        label="implement",
        kind="agent",
        gate="liveness",
        status="running",
        with_resolved={"consult": PLANNED, **resolved},
        consults=consults or {},
    )


def an_attempt(row: StepRun, n: int, role: str = "agent", end_sha: str | None = None) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=row.run_id,
        step_run_id=row.id,
        n=n,
        status="error",
        role=role,  # type: ignore[arg-type]
        end_sha=end_sha,
    )


def a_record(row: StepRun, event: str = "senior_answer", path: str = PATH) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=row.run_id,
        at=EPOCH,
        path=path,
        event=event,  # type: ignore[arg-type]
        actor="senior",
        payload={"mode": "session", "text": "t", "kind": "blocked"},
    )


# ── the decision file ────────────────────────────────────────────────────────


def test_an_answer_reads_its_status_reason_and_body() -> None:
    decision = consult.parse("---\nstatus: answer\nreason: clear\n---\n\nUse the v2 route.\n")

    assert decision == consult.Decision(status="answer", reason="clear", body="Use the v2 route.")


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "no frontmatter at all",
        "---\nstatus: answer\n",
        "---\n- a list\n---\n",
        "---\nreason: none\n---\nbody",
        "---\nstatus: maybe\n---\nbody",
        "---\nstatus: [answer]\n---\nbody",
        "---\nstatus: answer: : :\n---\n",
    ],
)
def test_an_unreadable_file_is_no_decision(text: str | None) -> None:
    assert consult.parse(text) is None


def test_a_reason_that_is_not_text_reads_empty() -> None:
    decision = consult.parse("---\nstatus: escalate\nreason: [a, b]\n---\n")

    assert decision == consult.Decision(status="escalate", reason="", body="")


def test_an_answer_with_a_body_is_the_answer() -> None:
    decision = consult.Decision(status="answer", reason="", body="Do X.")

    assert consult.verdict(decision) == ("answer", "Do X.")


def test_an_escalation_carries_its_reason() -> None:
    decision = consult.Decision(status="escalate", reason="product call", body="")

    assert consult.verdict(decision) == ("escalate", "product call")


@pytest.mark.parametrize(
    "decision",
    [
        None,
        consult.Decision(status="answer", reason="r", body=""),
        consult.Decision(status="accept", reason="r", body="tests/a.py"),
    ],
    ids=["missing", "empty answer", "accept until 1-5"],
)
def test_everything_else_fails_closed(decision: consult.Decision | None) -> None:
    assert consult.verdict(decision) == ("failed", "")


def test_the_decision_file_is_named_by_row_and_attempt_inside_the_ignored_folder() -> None:
    assert consult.decision_path(5, 3) == ".orchestrator/consult/005-3.decision.md"
    assert consult.IGNORE_FILE == ".orchestrator/.gitignore"
    assert consult.IGNORE_ALL.strip() == "*"


# ── what is offered ──────────────────────────────────────────────────────────


def test_a_declared_unused_kind_is_offered() -> None:
    row = a_row()

    assert consult.offered(row.with_resolved, row.consults, "blocked")


@pytest.mark.parametrize(
    ("with_resolved", "consults", "kind"),
    [
        ({}, {}, "blocked"),
        ({"consult": "not a block"}, {}, "blocked"),
        ({"consult": {**PLANNED, "on": "blocked"}}, {}, "blocked"),
        ({"consult": PLANNED}, {"blocked": {"state": "escalate"}}, "blocked"),
        ({"consult": PLANNED}, {}, "protected_path"),
    ],
    ids=["no consult", "not a mapping", "on not a list", "used", "other kind"],
)
def test_nothing_else_is_offered(
    with_resolved: dict[str, Any], consults: dict[str, Any], kind: str
) -> None:
    assert not consult.offered(with_resolved, consults, kind)


def test_the_due_entry_is_found_by_its_state() -> None:
    entry = {"state": "due", "question": "q"}

    assert consult.due({"x": {"state": "answer"}, "blocked": entry}) == ("blocked", entry)
    assert consult.due({"blocked": {"state": "failed"}, "y": "junk"}) is None


# ── filling a clause ─────────────────────────────────────────────────────────


def test_a_clause_is_filled_once_and_unknown_tokens_stay() -> None:
    clause = "Run {skill} on {story_id} in {spec_folder}: {condition} → {decision} {other}"
    values = {
        "skill": "senior-consult",
        "story_id": "1",
        "spec_folder": "/s",
        "condition": "{answer}",
        "decision": "/d",
    }

    filled = consult.fill(clause, values)

    assert filled == "Run senior-consult on 1 in /s: {answer} → /d {other}"


def test_the_answer_text_is_the_consults_own_clause() -> None:
    row = a_row()

    assert consult.answer_text(row.with_resolved, "why?", "because") == 'Senior on "why?": because'


def test_an_answer_text_with_no_clause_is_the_body() -> None:
    assert consult.answer_text({}, "why?", "because") == "because"


# ── delivery ─────────────────────────────────────────────────────────────────


def answered(answered_by: int = 2) -> dict[str, Any]:
    return {"blocked": {"state": "answer", "answered_by": answered_by}}


def test_the_latest_senior_answer_is_delivered_until_an_agent_attempt_ends() -> None:
    row = a_row(answered())
    older, newer = a_record(row), a_record(row)
    attempts = [an_attempt(row, 1, end_sha="a"), an_attempt(row, 2, "consult", "b")]
    attempts.append(an_attempt(row, 3))

    assert consult.delivers(row, attempts, [older, newer]) == newer


def test_nothing_is_delivered_once_the_resumed_attempt_came_back() -> None:
    row = a_row(answered())
    attempts = [an_attempt(row, 1, end_sha="a"), an_attempt(row, 3, end_sha="c")]

    assert consult.delivers(row, attempts, [a_record(row)]) is None


def test_a_consult_attempt_above_the_answer_does_not_end_the_delivery() -> None:
    row = a_row(answered())
    attempts = [an_attempt(row, 4, "consult", end_sha="d")]
    answer = a_record(row)

    assert consult.delivers(row, attempts, [answer]) == answer


@pytest.mark.parametrize(
    "consults",
    [{}, {"blocked": {"state": "due"}}, {"blocked": {"state": "answer"}}, {"blocked": "junk"}],
    ids=["none", "due", "answer without attempt", "not a mapping"],
)
def test_nothing_is_delivered_without_an_answered_entry(consults: dict[str, Any]) -> None:
    row = a_row(consults)

    assert consult.delivers(row, [], [a_record(row)]) is None


def test_only_this_rows_senior_answer_is_delivered() -> None:
    row = a_row(answered())
    records = [a_record(row, path="stories[1].implement"), a_record(row, event="consult")]

    assert consult.delivers(row, [], records) is None


def test_a_recorded_result_without_the_field_still_deserializes() -> None:
    restored = StepResult.model_validate({"status": "done", "gate": "liveness"})

    assert restored.consult is None
