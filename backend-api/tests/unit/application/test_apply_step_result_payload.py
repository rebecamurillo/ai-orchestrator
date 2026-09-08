"""`StepResult.payload`, and the one write that keeps it (AD-8, AD-17).

AD-17 says a protected-path stop records *which* files were touched, and the gate record is
the append-only place a Run's reasons live. The executor cannot write one — it returns the
values and `apply_step_result` writes them, in the unit of work it already opened — so the
payload travels on the result and lands on the `park` record beside the reason.

Only the park path carries it. A `retry_auto` line, a `redispatch` line and the Run's own
`done` line are written by rules that decided them here, out of facts they hold themselves;
a payload on those would be an executor writing state through a side door.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.values import Park, Retry, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt

HITS = {"hits": [{"path": "specs/x/SPEC.md", "kind": "modified"}]}
REASON = "protected path modified: specs/x/SPEC.md"
ROW = "plan"


def a_parked_run(result: StepResult) -> World:
    world = a_world("running", PAIR_PLAN, {ROW: "running"})
    an_attempt(world, ROW, n=1)
    apply_step_result(world.ports, world.run.id, world.row(ROW).seq, result)
    return world


def a_park(**over: Any) -> StepResult:
    fields: dict[str, Any] = {
        "status": "error",
        "gate": "liveness",
        "reason": REASON,
        "park": Park(kind="protected_path", reason=REASON, path=ROW),
        "payload": HITS,
    }
    fields.update(over)
    return StepResult(**fields)


def parks(world: World) -> list[GateRecord]:
    return [line for line in world.records() if line.event == "protected_path"]


def test_a_result_carries_no_payload_unless_it_was_given_one() -> None:
    assert StepResult(status="done", gate="liveness").payload == {}


def test_the_payload_lands_on_the_park_record_beside_the_reason() -> None:
    world = a_parked_run(a_park())

    assert [line.payload for line in parks(world)] == [HITS]
    assert [line.text for line in parks(world)] == [REASON]


def test_a_park_that_carried_none_records_none() -> None:
    world = a_parked_run(a_park(payload={}))

    assert [line.payload for line in parks(world)] == [{}]


def test_the_record_is_a_copy_the_caller_cannot_reach_back_into() -> None:
    """The gate record is append-only: a mapping the executor still holds is not one."""
    payload: dict[str, Any] = {"hits": []}
    world = a_parked_run(a_park(payload=payload))
    payload["hits"] = ["late"]

    assert [line.payload for line in parks(world)] == [{"hits": []}]


def test_a_retry_line_carries_no_payload() -> None:
    """`retry_auto` is `apply_step_result`'s own record, out of facts it holds itself."""
    world = a_world("running", PAIR_PLAN, {ROW: "running"})
    an_attempt(world, ROW, n=1)

    apply_step_result(
        world.ports,
        world.run.id,
        world.row(ROW).seq,
        StepResult(
            status="error",
            gate="liveness",
            reason="unexpected status: draft",
            retry=Retry(prompt="again", max=2),
            payload=HITS,
        ),
    )

    assert [line.payload for line in world.records() if line.event == "retry_auto"] == [{}]
