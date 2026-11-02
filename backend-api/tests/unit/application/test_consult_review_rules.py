"""`rules/consult.py` at a `protected_path` stop (story 1-8, spine AD-17/AD-22, hard rule 1 as
amended 2026-11-02): an `accept` or an escalation is read there and nothing else, the diff file
sits beside the decision file, and a senior's acceptance is delivered only to the `agent`
attempt right after the consult that made it, before any blocked answer."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.rules import consult
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Consult
from tests.unit.application.test_consult_rules import PATH, a_record, a_row, an_attempt
from tests.unit.fakes.clock import EPOCH

ACCEPTED = {"protected_path": {"state": "accept", "answered_by": 2}}


def an_accept(row: StepRun, kind: str = "protected_path", path: str = PATH) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=row.run_id,
        at=EPOCH,
        path=path,
        event="senior_accept",
        actor="senior",
        payload={"files": ["tests/a.py"], "reason": "AC 2", "kind": kind},
    )


def attempts(row: StepRun, *roles: str) -> list[Attempt]:
    return [an_attempt(row, n, role) for n, role in enumerate(roles, start=1)]


# ── the decision at a protected_path stop ────────────────────────────────────


def test_an_accept_carries_its_reason() -> None:
    decision = consult.Decision(status="accept", reason="AC 2", body="", approved_files=("a",))

    assert consult.verdict(decision, "protected_path") == ("accept", "AC 2")


def test_an_escalation_carries_its_reason() -> None:
    decision = consult.Decision(status="escalate", reason="unrelated test", body="")

    assert consult.verdict(decision, "protected_path") == ("escalate", "unrelated test")


@pytest.mark.parametrize(
    "decision",
    [None, consult.Decision(status="answer", reason="r", body="Revise it.")],
    ids=["missing", "an answer"],
)
def test_everything_else_fails_closed(decision: consult.Decision | None) -> None:
    assert consult.verdict(decision, "protected_path") == ("failed", "")


def test_an_accept_at_a_blocked_stop_stays_unreadable() -> None:
    decision = consult.Decision(status="accept", reason="r", body="b")

    assert consult.verdict(decision, "blocked") == ("failed", "")


def test_the_diff_file_sits_beside_the_decision_file() -> None:
    assert consult.diff_path(5, 3) == ".orchestrator/consult/005-3.diff"
    assert consult.decision_path(5, 3).startswith(".orchestrator/consult/005-3.")


def test_an_offer_carries_the_hits_payload() -> None:
    assert Consult(kind="protected_path", question="q").hits == {}
    hits = {"hits": [{"path": "tests/a.py", "kind": "modified"}]}

    assert Consult(kind="protected_path", question="q", hits=hits).hits == hits


# ── delivering an acceptance ─────────────────────────────────────────────────


def test_an_acceptance_is_delivered_to_the_agent_attempt_after_the_consult() -> None:
    row = a_row(ACCEPTED)
    accept = an_accept(row)

    found = consult.delivers(row, attempts(row, "agent", "consult", "agent"), [accept])

    assert found == accept


def test_the_latest_acceptance_of_that_kind_is_delivered() -> None:
    row = a_row(ACCEPTED)
    older, newer = an_accept(row), an_accept(row)

    assert consult.delivers(row, attempts(row, "agent", "consult", "agent"), [older, newer]) == (
        newer
    )


def test_a_later_attempt_is_not_delivered_the_acceptance_again() -> None:
    row = a_row(ACCEPTED)
    later = attempts(row, "agent", "consult", "agent", "agent")

    assert consult.delivers(row, later, [an_accept(row)]) is None


def test_a_consult_attempt_numbered_after_the_consult_is_not_delivered_it() -> None:
    row = a_row(ACCEPTED)

    assert consult.delivers(
        row, attempts(row, "agent", "consult", "consult"), [an_accept(row)]
    ) is (None)


def test_the_acceptance_is_checked_before_the_blocked_answer() -> None:
    row = a_row({**ACCEPTED, "blocked": {"state": "answer", "answered_by": 2}})
    accept = an_accept(row)

    found = consult.delivers(
        row, attempts(row, "agent", "consult", "agent"), [a_record(row), accept]
    )

    assert found == accept


@pytest.mark.parametrize(
    "records",
    [
        [],
        ["blocked kind"],
        ["other row"],
    ],
    ids=["no record", "a blocked acceptance", "another row's"],
)
def test_only_this_rows_protected_path_acceptance_is_delivered(records: list[str]) -> None:
    row = a_row(ACCEPTED)
    made = {
        "blocked kind": lambda: an_accept(row, kind="blocked"),
        "other row": lambda: an_accept(row, path="stories[1].implement"),
    }

    found = consult.delivers(
        row, attempts(row, "agent", "consult", "agent"), [made[r]() for r in records]
    )

    assert found is None


@pytest.mark.parametrize(
    "entry",
    [
        {"state": "failed", "answered_by": 2},
        {"state": "accept"},
        {"state": "accept", "answered_by": "2"},
        "junk",
    ],
    ids=["not accepted", "no consult attempt", "not a number", "not a mapping"],
)
def test_nothing_is_delivered_without_an_accepted_entry(entry: Any) -> None:
    row = a_row({"protected_path": entry})

    found = consult.delivers(row, attempts(row, "agent", "consult", "agent"), [an_accept(row)])

    assert found is None


def test_a_row_with_no_attempt_is_delivered_nothing() -> None:
    row = a_row(ACCEPTED)

    assert consult.delivers(row, [], [an_accept(row)]) is None
