"""The senior's acceptance, through `apply_step_result` (story 1-5, spine AD-8/AD-17/AD-22,
2026-11-02): an answer naming files extends `run.accepted_paths` without duplicates and
records one `senior_accept` (actor `senior`) before its `senior_answer`, in the same unit of
work. Nothing is accepted when the result carries a park."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases.apply_consult import apply_consult
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.test_consult_apply import (
    BUILD,
    QUESTION,
    a_running_world,
    apply,
)
from tests.unit.application.writer_fixtures import World, an_attempt

DUE = {"blocked": {"state": "due", "question": QUESTION, "snapshot": {}}}


def an_approving_answer(
    files: tuple[str, ...], reason: str = "AC 2 changes it", **over: Any
) -> StepResult:
    fields: dict[str, Any] = {
        "status": "error",
        "gate": "liveness",
        "reason": "senior answered: Revise it.",
        "consult": Consult(
            kind="blocked",
            question=QUESTION,
            outcome="answer",
            answer="Revise tests/a.py.",
            approved_files=files,
            reason=reason,
        ),
    }
    fields.update(over)
    return StepResult(**fields)


def a_consulted_world(accepted: tuple[str, ...] = ()) -> World:
    world = a_running_world(consults=DUE)
    if accepted:
        world.ports.runs.update(world.stored_run().model_copy(update={"accepted_paths": accepted}))
    an_attempt(world, BUILD, n=1)
    an_attempt(world, BUILD, n=2)
    return world


def test_the_files_are_accepted_and_recorded_before_the_answer() -> None:
    world = a_consulted_world()

    apply(world, an_approving_answer(("tests/a.py", "tests/b.py")))

    assert world.stored_run().accepted_paths == ("tests/a.py", "tests/b.py")
    assert world.events() == ["senior_accept", "senior_answer"]
    accept = world.records()[0]
    assert (accept.actor, accept.path, accept.attempt_n) == ("senior", BUILD, 2)
    assert accept.text == "accepted by the senior: tests/a.py, tests/b.py · AC 2 changes it"
    assert accept.payload == {
        "files": ["tests/a.py", "tests/b.py"],
        "reason": "AC 2 changes it",
        "kind": "blocked",
    }
    assert world.stored_run().status == "running"
    assert world.row(BUILD).status == "queued"


@pytest.mark.parametrize("reason", ["", "   "])
def test_files_with_no_reason_are_never_accepted(reason: str) -> None:
    """AD-17's amendment: the record names the senior and the reason, or there is none."""
    world = a_consulted_world()

    apply(world, an_approving_answer(("tests/a.py",), reason=reason))

    assert "senior_accept" not in world.events()
    assert world.stored_run().accepted_paths == ()


def test_the_list_gains_no_duplicate() -> None:
    world = a_consulted_world(accepted=("tests/a.py", "docs/x.md"))

    apply(world, an_approving_answer(("tests/a.py", "tests/b.py", "tests/b.py")))

    assert world.stored_run().accepted_paths == ("tests/a.py", "docs/x.md", "tests/b.py")
    assert world.records()[0].payload["files"] == ["tests/a.py", "tests/b.py"]


def test_an_answer_naming_no_file_records_no_acceptance() -> None:
    world = a_consulted_world()

    apply(world, an_approving_answer(()))

    assert world.events() == ["senior_answer"]
    assert world.stored_run().accepted_paths == ()


def test_nothing_is_accepted_when_the_answer_parks() -> None:
    world = a_consulted_world()
    reason = f"{QUESTION} · senior answered: Revise it."
    parked = an_approving_answer(
        ("tests/a.py",),
        status="blocked",
        park=Park(kind="blocked", reason=reason, path=BUILD),
    )

    apply(world, parked)

    assert "senior_accept" not in world.events()
    assert world.stored_run().accepted_paths == ()


def test_the_run_returned_carries_the_accepted_list() -> None:
    world = a_consulted_world()
    run, row = world.stored_run(), world.row(BUILD).model_copy(update={"status": "error"})

    updated = apply_consult(world.ports, run, row, an_approving_answer(("tests/a.py",)), None)

    assert updated is not None
    assert updated.accepted_paths == ("tests/a.py",)
