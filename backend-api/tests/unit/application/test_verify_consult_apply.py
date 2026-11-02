"""`apply_consult` for a `verify_failed` consult (story 1-6, spine AD-8/AD-22, 2026-11-02).

An answer is recorded as `senior_answer` on the target row with no `mode`: it is a diagnosis
for one further fresh redispatch, counted on `redispatch_count`, never a message into a
session. Any other outcome marks the entry, returns the target to `done`, and parks the
verify row's stop."""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.verify_consult_fixtures import (
    BLOCK,
    BUILD,
    HEAD,
    MAX,
    QUESTION,
    VERIFY,
    a_verify_world,
    an_answer,
)
from tests.unit.application.writer_fixtures import World, an_attempt

DUE: dict[str, Any] = {
    "state": "due",
    "question": QUESTION,
    "snapshot": {"tree": {"head": HEAD, "status": ""}},
    "declared": BLOCK,
    "park_path": VERIFY,
}


def a_consulting_world(**over: Any) -> World:
    """The build row `running` its consult attempt (4) after agent attempt 3."""
    world = a_verify_world(build="running", consults={"verify_failed": dict(DUE)}, **over)
    an_attempt(world, BUILD, n=3, status="done", end_sha="e" * 40)
    an_attempt(world, BUILD, n=4, role="consult")
    return world


def apply(world: World, result: StepResult) -> None:
    apply_step_result(world.ports, world.run.id, world.row(BUILD).seq, result)


def a_closed(kind: str = "escalate", reason: str = "no view") -> StepResult:
    shown = f"{QUESTION} · senior: {reason}"
    return StepResult(
        status="done",
        gate="liveness",
        reason=shown,
        park=Park(kind="verify_failed", reason=shown, path=VERIFY),
        consult=Consult(kind="verify_failed", question=QUESTION, outcome=kind),  # type: ignore[arg-type]
    )


# ── the senior's diagnosis ───────────────────────────────────────────────────


def test_an_answer_requeues_the_target_as_one_further_counted_redispatch() -> None:
    world = a_consulting_world()

    apply(world, an_answer())

    build = world.row(BUILD)
    assert build.status == "queued"
    assert build.redispatch_count == MAX + 1
    assert build.retry_count == 0
    assert world.stored_run().status == "running"


def test_the_entry_reads_answer_and_keeps_the_block_it_ran_on() -> None:
    world = a_consulting_world()

    apply(world, an_answer())

    assert world.row(BUILD).consults["verify_failed"] == {
        **DUE,
        "state": "answer",
        "answered_by": 4,
    }


def test_the_diagnosis_is_recorded_without_a_session_mode() -> None:
    world = a_consulting_world()

    apply(world, an_answer("The mock is stale."))

    [line] = world.records()
    assert (line.event, line.actor, line.path, line.attempt_n) == (
        "senior_answer",
        "senior",
        BUILD,
        4,
    )
    assert line.text == "The mock is stale."
    assert line.payload == {
        "kind": "verify_failed",
        "text": 'Diagnosis of "verify failed 3/3": The mock is stale.',
    }


def test_the_consult_attempt_closes_error_and_the_verify_row_is_untouched() -> None:
    world = a_consulting_world()

    apply(world, an_answer())

    attempt = world.attempts_of(BUILD)[-1]
    assert (attempt.n, attempt.role, attempt.status) == (4, "consult", "error")
    assert world.status_of(VERIFY) == "running"


# ── every other outcome ──────────────────────────────────────────────────────


def test_an_escalation_marks_the_entry_and_parks_the_verify_stop() -> None:
    world = a_consulting_world()

    apply(world, a_closed("escalate", "needs a product call"))

    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_path) == ("needs_you", "verify_failed", VERIFY)
    assert run.park_reason == f"{QUESTION} · senior: needs a product call"
    assert world.row(BUILD).consults["verify_failed"]["state"] == "escalate"


def test_the_target_returns_to_done_and_is_not_counted() -> None:
    world = a_consulting_world()

    apply(world, a_closed("failed"))

    build = world.row(BUILD)
    assert (build.status, build.redispatch_count) == ("done", MAX)
    assert world.row(BUILD).consults["verify_failed"]["state"] == "failed"
    assert world.events() == ["verify_failed"]


def test_a_closed_consult_drops_the_orphan_group_it_was_handed() -> None:
    entry = {**DUE, "orphan_pgid": 4242}
    world = a_verify_world(build="running", consults={"verify_failed": entry})
    an_attempt(world, BUILD, n=4, role="consult")

    apply(world, a_closed("escalate"))

    assert "orphan_pgid" not in world.row(BUILD).consults["verify_failed"]
