"""`gate_verdict_of` reads the stored verdict from repositories alone (epic 8 story 2, AC7)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.use_cases.initiative_advance import AdvancePorts, gate_verdict_of
from orchestrator.domain.values import GateVerdict
from tests.unit.application.initiative_world import InitiativeWorld
from tests.unit.application.steps.agent_fixtures import an_attempt
from tests.unit.application.writer_fixtures import build_rows, build_run
from tests.unit.fakes.runs import FakeAttemptRepository, FakeStepRunRepository

PLAN = (("plan", "plan.check"), ("gate", "agent"), ("after", "shell"))


def ports_with(
    role: str | None = "spec-gate", **attempt_over: object
) -> tuple[AdvancePorts, object]:
    world = InitiativeWorld()
    run = build_run("done")
    rows = build_rows(run.id, PLAN)
    if role is not None:
        rows[1] = rows[1].model_copy(update={"role": role})
    steps = FakeStepRunRepository(rows)
    attempts = FakeAttemptRepository()
    if attempt_over is not None:
        attempts.add(an_attempt(rows[1], 1, status="done", **attempt_over))
    base = AdvancePorts(
        initiatives=world.initiatives,
        advances=world.advances,
        runs=world.runs,
        create_run=world.create_ports,
        uow=world.uow,
        clock=world.harness.clock,
    )
    return replace(base, steps=steps, attempts=attempts), run


def test_the_stored_verdict_is_returned() -> None:
    ports, run = ports_with(
        verdict_word="fail", verdict_fields={"owners": ["ux"]}, verdict_text="- a"
    )

    assert gate_verdict_of(ports, run.id) == GateVerdict(  # type: ignore[attr-defined]
        word="fail", fields={"owners": ["ux"]}, text="- a"
    )


def test_a_run_without_a_gate_row_has_none() -> None:
    ports, run = ports_with(role="implement", verdict_word="pass")

    assert gate_verdict_of(ports, run.id) is None  # type: ignore[attr-defined]


def test_an_attempt_that_stored_no_word_has_none() -> None:
    ports, run = ports_with()

    assert gate_verdict_of(ports, run.id) is None  # type: ignore[attr-defined]


def test_a_gate_row_with_no_attempt_has_none() -> None:
    ports, run = ports_with(role="spec-gate", verdict_word="pass")
    emptied = replace(ports, attempts=FakeAttemptRepository())

    assert gate_verdict_of(emptied, run.id) is None  # type: ignore[attr-defined]


def test_a_null_fields_and_text_read_as_empty() -> None:
    ports, run = ports_with(verdict_word="pass")

    assert gate_verdict_of(ports, run.id) == GateVerdict(word="pass")  # type: ignore[attr-defined]


def test_ports_without_steps_or_attempts_have_none() -> None:
    ports, run = ports_with(verdict_word="pass")

    assert gate_verdict_of(replace(ports, steps=None), run.id) is None  # type: ignore[attr-defined]
    assert gate_verdict_of(replace(ports, attempts=None), run.id) is None  # type: ignore[attr-defined]
