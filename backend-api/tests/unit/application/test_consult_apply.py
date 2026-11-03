"""`apply_consult`, through `apply_step_result` (story 1-4, spine AD-8/AD-22, 2026-11-02).

An offer records `consult` (actor `machine`), writes the entry `due` and requeues the row
through `retry`'s transition without counting a retry. An answer records `senior_answer`
(actor `senior`) and requeues. Every other outcome marks the entry and parks as routed. The
Run never leaves `running` while a consult is in flight."""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.apply_consult import apply_consult
from orchestrator.application.use_cases.apply_step_result import (
    apply_step_result,
    budget_second_record,
)
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt

BUILD = "stories[0].build"
QUESTION = "## Auto Run Result\n\nStatus: blocked\nBlocking condition: intent gap"
SNAPSHOT = {"tree": {"head": "a" * 40, "status": ""}}
ANSWER_CLAUSE = 'Senior to "{condition}": {answer}'
CONSULT = {
    "model": "senior",
    "harness": "",
    "skill": "senior-consult",
    "on": ["blocked"],
    "timeout_min": None,
    "prompts": {"dispatch": "d", "answer": ANSWER_CLAUSE},
}


def a_running_world(on_fail: str | None = None, consults: dict[str, Any] | None = None) -> World:
    resolved: dict[str, Any] = {"consult": CONSULT}
    if on_fail is not None:
        resolved["on_fail"] = on_fail
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, {BUILD: resolved})
    if consults is not None:
        world.ports.steps.update(world.row(BUILD).model_copy(update={"consults": consults}))
    return world


def an_offer() -> StepResult:
    return StepResult(
        status="error",
        gate="liveness",
        reason=f"consult: {QUESTION}",
        output_ref="/work/logs/005-1.log",
        consult=Consult(kind="blocked", question=QUESTION, snapshot=SNAPSHOT),
    )


def apply(world: World, result: StepResult) -> None:
    apply_step_result(
        world.ports,
        world.run.id,
        world.row(BUILD).seq,
        result,
        after_route=lambda run, row, res: budget_second_record(world.ports, run, row, res),
    )


# ── the offer ────────────────────────────────────────────────────────────────


def test_an_offer_records_consult_and_requeues_the_row_without_a_retry() -> None:
    world = a_running_world()
    an_attempt(world, BUILD, n=1)

    apply(world, an_offer())

    row = world.row(BUILD)
    assert row.status == "queued"
    assert row.retry_count == 0
    assert row.reason == f"consult: {QUESTION}"
    assert row.consults == {"blocked": {"state": "due", "question": QUESTION, "snapshot": SNAPSHOT}}
    [line] = world.records()
    assert (line.event, line.actor, line.path, line.attempt_n) == ("consult", "machine", BUILD, 1)
    assert line.text == QUESTION
    assert line.payload == {"kind": "blocked"}
    assert world.stored_run().status == "running"


def test_the_stopped_agent_attempt_closes_error() -> None:
    world = a_running_world()
    an_attempt(world, BUILD, n=1)

    apply(world, an_offer())

    [attempt] = world.attempts_of(BUILD)
    assert attempt.status == "error"
    assert attempt.ended_at is not None


def test_an_offer_on_a_row_declaring_on_fail_fail_does_not_fail_the_run() -> None:
    world = a_running_world(on_fail="fail")
    an_attempt(world, BUILD, n=1)

    apply(world, an_offer())

    assert world.stored_run().status == "running"
    assert world.row(BUILD).status == "queued"
    assert "failed" not in world.events()


# ── the senior's answer ──────────────────────────────────────────────────────


def an_answer(**over: Any) -> StepResult:
    fields: dict[str, Any] = {
        "status": "error",
        "gate": "liveness",
        "reason": "senior answered: Use v2.",
        "consult": Consult(
            kind="blocked", question=QUESTION, outcome="answer", answer="Use v2.\nThen stop."
        ),
    }
    fields.update(over)
    return StepResult(**fields)


def a_consulted_world() -> World:
    entry = {"state": "due", "question": QUESTION, "snapshot": SNAPSHOT, "orphan_pgid": 12}
    world = a_running_world(consults={"blocked": entry})
    an_attempt(world, BUILD, n=1, status="error", ended_at=world.clock.now())
    an_attempt(world, BUILD, n=2, role="consult")
    return world


def test_an_answer_records_senior_answer_and_requeues_the_row() -> None:
    world = a_consulted_world()

    apply(world, an_answer())

    row = world.row(BUILD)
    assert row.status == "queued"
    assert row.retry_count == 0
    assert row.consults["blocked"] == {
        "state": "answer",
        "question": QUESTION,
        "snapshot": SNAPSHOT,
        "answered_by": 2,
    }
    [line] = world.records()
    assert (line.event, line.actor, line.path, line.attempt_n) == (
        "senior_answer",
        "senior",
        BUILD,
        2,
    )
    assert line.text == "Use v2.\nThen stop."
    assert line.payload == {
        "mode": "session",
        "text": f'Senior to "{QUESTION}": Use v2.\nThen stop.',
        "kind": "blocked",
    }
    assert world.stored_run().status == "running"


def test_the_consult_attempt_closes_with_the_status_it_reached() -> None:
    world = a_consulted_world()

    apply(world, an_answer())

    consult = world.attempts_of(BUILD)[-1]
    assert (consult.role, consult.status) == ("consult", "error")


def test_an_escalation_marks_the_entry_and_parks_blocked() -> None:
    world = a_consulted_world()
    reason = f"{QUESTION} · senior: product call"

    apply(
        world,
        StepResult(
            status="blocked",
            gate="liveness",
            reason=reason,
            park=Park(kind="blocked", reason=reason, path=BUILD),
            consult=Consult(kind="blocked", question=QUESTION, outcome="escalate"),
        ),
    )

    assert world.row(BUILD).consults["blocked"]["state"] == "escalate"
    assert world.events() == ["blocked"]
    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_reason) == ("needs_you", "blocked", reason)


def test_an_answer_over_budget_parks_blocked_with_the_budget_record_on_top() -> None:
    world = a_consulted_world()
    reason = f"{QUESTION} · senior answered: Use v2."

    apply(
        world,
        an_answer(
            status="blocked",
            reason=reason,
            park=Park(kind="blocked", reason=reason, path=BUILD),
            budget_park=Park(kind="budget", reason="budget $12.00 / $10.00"),
        ),
    )

    assert world.events() == ["blocked", "budget"]
    assert world.stored_run().park_kind == "budget"
    entry = world.row(BUILD).consults["blocked"]
    assert entry["state"] == "answer"
    assert "answered_by" not in entry


def test_a_result_without_a_consult_is_left_to_the_ordinary_routing() -> None:
    world = a_running_world()
    run = world.stored_run()

    assert (
        apply_consult(
            world.ports,
            run,
            world.row(BUILD),
            an_offer().model_copy(update={"consult": None}),
            None,
        )
        is None
    )
