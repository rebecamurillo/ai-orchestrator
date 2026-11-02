"""`rules/consult.py` for the `verify_failed` consult (story 1-6, spine AD-22, 2026-11-02): the
block a `run` row's `on_fail` carries, the block a due entry carries with it, the diagnosis a
fresh redispatch is owed, and the tokens the senior's dispatch clause may name.

The diagnosis never travels as a `resume_signal`: `delivers` is the `blocked` consult's alone."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.rules import consult
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import EPOCH

PATH = "stories[0].implement"
BLOCK = {
    "model": "senior",
    "harness": "",
    "skill": "senior-consult",
    "on": ["verify_failed"],
    "timeout_min": None,
    "prompts": {"dispatch": "d", "answer": 'Diagnosis of "{condition}": {answer}'},
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
        with_resolved=resolved,
        consults=consults or {},
    )


def an_attempt(row: StepRun, n: int, role: str = "agent", end_sha: str | None = None) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=row.run_id,
        step_run_id=row.id,
        n=n,
        status="done",
        role=role,  # type: ignore[arg-type]
        started_at=EPOCH,
        end_sha=end_sha,
    )


def a_record(row: StepRun, kind: str | None = "verify_failed", text: str = "T") -> GateRecord:
    payload: dict[str, Any] = {"text": text}
    if kind is not None:
        payload["kind"] = kind
    return GateRecord(
        id=new_id(),
        run_id=row.run_id,
        at=EPOCH,
        event="senior_answer",
        actor="senior",
        path=row.path,
        text="raw",
        payload=payload,
    )


def diagnosed(answered_by: int = 3) -> dict[str, Any]:
    return {"verify_failed": {"state": "answer", "answered_by": answered_by}}


# ── the block ────────────────────────────────────────────────────────────────


def test_the_verify_block_is_the_consult_of_a_planned_redispatch() -> None:
    resolved = {"on_fail": {"target_seq": 4, "max": 2, "consult": BLOCK}}

    assert consult.verify_block(resolved) == BLOCK


@pytest.mark.parametrize(
    "resolved",
    [
        {},
        {"on_fail": "fail"},
        {"on_fail": {"target_seq": 4, "max": 2}},
        {"on_fail": {"consult": 1}},
    ],
    ids=["none", "plain action", "no consult", "not a mapping"],
)
def test_no_other_row_declares_a_verify_consult(resolved: dict[str, Any]) -> None:
    assert consult.verify_block(resolved) is None


def test_a_due_entrys_own_block_wins_over_the_rows() -> None:
    row_block = {**BLOCK, "skill": "blocked-skill"}
    entry = {"declared": BLOCK}

    assert consult.block_of({"consult": row_block}, entry) == BLOCK
    assert consult.block_of({"consult": row_block}, {}) == row_block
    assert consult.block_of({}, {"declared": "junk"}) == {}


def test_the_answer_text_reads_the_entrys_clause() -> None:
    entry = {"declared": BLOCK}

    text = consult.answer_text({}, "verify failed 3/3", "the mock is stale", entry)

    assert text == 'Diagnosis of "verify failed 3/3": the mock is stale'


# ── the tokens ───────────────────────────────────────────────────────────────


def test_the_failure_tokens_are_filled_in_a_dispatch_clause() -> None:
    clause = "{command} exited {code}: {tail} (log {log}) {unknown}"
    values = {"command": "make test", "code": "2", "tail": "boom", "log": "/work/1.log"}

    assert consult.fill(clause, values) == "make test exited 2: boom (log /work/1.log) {unknown}"


# ── the diagnosis ────────────────────────────────────────────────────────────


def test_the_diagnosis_is_owed_until_an_agent_attempt_after_the_consult_ends() -> None:
    row = a_row(diagnosed())
    records = [a_record(row, text="old"), a_record(row, text="new")]
    attempts = [an_attempt(row, 1, end_sha="a"), an_attempt(row, 3, "consult"), an_attempt(row, 4)]

    assert consult.diagnosis(row, attempts, records) == "new"


def test_nothing_is_owed_once_the_redispatched_agent_came_back() -> None:
    row = a_row(diagnosed())
    attempts = [an_attempt(row, 4, end_sha="d")]

    assert consult.diagnosis(row, attempts, [a_record(row)]) == ""


def test_a_consult_attempt_above_the_answer_does_not_end_the_debt() -> None:
    row = a_row(diagnosed())

    assert consult.diagnosis(row, [an_attempt(row, 4, "consult", "d")], [a_record(row)]) == "T"


@pytest.mark.parametrize(
    "consults",
    [
        {},
        {"verify_failed": {"state": "due"}},
        {"verify_failed": {"state": "answer"}},
        {"verify_failed": "junk"},
        {"blocked": {"state": "answer", "answered_by": 3}},
    ],
    ids=["none", "due", "answer without attempt", "not a mapping", "another kind"],
)
def test_nothing_is_owed_without_an_answered_verify_entry(consults: dict[str, Any]) -> None:
    row = a_row(consults)

    assert consult.diagnosis(row, [], [a_record(row)]) == ""


def test_only_this_rows_verify_answer_is_owed() -> None:
    row = a_row(diagnosed())
    elsewhere = a_record(row).model_copy(update={"path": "stories[1].implement"})
    records = [elsewhere, a_record(row, kind="blocked"), a_record(row, kind=None)]

    assert consult.diagnosis(row, [], records) == ""


def test_a_verify_answer_is_never_the_blocked_consults_delivery() -> None:
    row = a_row(diagnosed())

    assert consult.delivers(row, [], [a_record(row)]) is None


def test_a_blocked_answer_is_never_the_diagnosis() -> None:
    row = a_row({"blocked": {"state": "answer", "answered_by": 3}})
    record = a_record(row, kind="blocked")

    assert consult.delivers(row, [], [record]) == record
    assert consult.diagnosis(row, [], [record]) == ""
