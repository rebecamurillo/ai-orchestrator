"""The senior's acceptance of a `protected_path` hit, through `apply_step_result` (story 1-8,
spine AD-8/AD-17/AD-22, 2026-11-02). The offer stores the hits payload on the entry. An
`accept` extends `run.accepted_paths` without duplicates, records `senior_accept` with
`kind: protected_path` and no `senior_answer`, sets the entry
`{state: accept, answered_by}` and requeues the row. Nothing is accepted when it parks."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.test_consult_apply import BUILD, SNAPSHOT, a_running_world, apply
from tests.unit.application.writer_fixtures import World, an_attempt

QUESTION = "protected path modified: tests/a.py · story done"
HITS = {"hits": [{"path": "tests/a.py", "kind": "modified"}]}
CONSULT_N = 2
DUE = {"protected_path": {"state": "due", "question": QUESTION, "snapshot": SNAPSHOT, "hits": HITS}}


def an_offer() -> StepResult:
    return StepResult(
        status="error",
        gate="liveness",
        reason=f"consult: {QUESTION}",
        consult=Consult(kind="protected_path", question=QUESTION, snapshot=SNAPSHOT, hits=HITS),
    )


def an_acceptance(
    files: tuple[str, ...] = ("tests/a.py",), reason: str = "AC 2 changes it", **over: Any
) -> StepResult:
    fields: dict[str, Any] = {
        "status": "error",
        "gate": "liveness",
        "reason": "senior accepted: tests/a.py",
        "consult": Consult(
            kind="protected_path",
            question=QUESTION,
            outcome="accept",
            approved_files=files,
            reason=reason,
        ),
    }
    fields.update(over)
    return StepResult(**fields)


def an_accepting_world(accepted: tuple[str, ...] = ()) -> World:
    world = a_running_world(consults=DUE)
    if accepted:
        world.ports.runs.update(world.stored_run().model_copy(update={"accepted_paths": accepted}))
    an_attempt(world, BUILD, n=1)
    an_attempt(world, BUILD, n=2)
    return world


def test_an_offer_stores_the_hits_payload_on_the_entry() -> None:
    world = a_running_world()
    an_attempt(world, BUILD, n=1)

    apply(world, an_offer())

    assert world.row(BUILD).consults == DUE
    assert world.events() == ["consult"]
    assert world.records()[0].payload == {"kind": "protected_path"}
    assert world.row(BUILD).status == "queued"


def test_an_acceptance_extends_the_list_records_it_and_requeues() -> None:
    world = an_accepting_world()

    apply(world, an_acceptance())

    assert world.stored_run().accepted_paths == ("tests/a.py",)
    assert world.events() == ["senior_accept"]
    accept = world.records()[0]
    assert (accept.actor, accept.path, accept.attempt_n) == ("senior", BUILD, 2)
    assert accept.text == "accepted by the senior: tests/a.py · AC 2 changes it"
    assert accept.payload == {
        "files": ["tests/a.py"],
        "reason": "AC 2 changes it",
        "kind": "protected_path",
    }
    row = world.row(BUILD)
    assert row.status == "queued"
    assert row.retry_count == 0
    assert row.consults["protected_path"]["state"] == "accept"
    assert row.consults["protected_path"]["answered_by"] == CONSULT_N
    assert world.stored_run().status == "running"


def test_the_list_gains_no_duplicate() -> None:
    world = an_accepting_world(accepted=("tests/a.py", "docs/x.md"))

    apply(world, an_acceptance(("tests/a.py", "tests/b.py")))

    assert world.stored_run().accepted_paths == ("tests/a.py", "docs/x.md", "tests/b.py")


def test_a_hub_acceptance_keeps_its_workdir_spelling() -> None:
    world = an_accepting_world()

    apply(world, an_acceptance(("repos/member/tests/a.py",)))

    assert world.stored_run().accepted_paths == ("repos/member/tests/a.py",)


@pytest.mark.parametrize(
    ("files", "reason"), [((), "AC 2"), (("tests/a.py",), ""), (("tests/a.py",), "  ")]
)
def test_an_acceptance_without_files_or_reason_accepts_nothing(
    files: tuple[str, ...], reason: str
) -> None:
    world = an_accepting_world()

    apply(world, an_acceptance(files, reason=reason))

    assert world.events() == []
    assert world.stored_run().accepted_paths == ()


def test_nothing_is_written_when_the_acceptance_parks() -> None:
    world = an_accepting_world()
    reason = f"{QUESTION} · consult failed: no remaining budget"
    parked = an_acceptance(park=Park(kind="protected_path", reason=reason, path=BUILD))

    apply(world, parked)

    assert "senior_accept" not in world.events()
    assert world.stored_run().accepted_paths == ()
    assert world.stored_run().park_kind == "protected_path"
    assert "answered_by" not in world.row(BUILD).consults["protected_path"]
