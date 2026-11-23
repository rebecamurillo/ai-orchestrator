"""The session a `conversation` park opens, and the skill its first turn starts with
(epic 4 story 4, AC1-AC3, AC5)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.rules import conversation
from orchestrator.application.use_cases.apply_step_result import (
    apply_step_result,
    budget_second_record,
)
from orchestrator.application.use_cases.conversation_session import (
    STARTED_TEXT,
    open_step_session,
)
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.session_turn import run_turn
from orchestrator.application.use_cases.session_view import session_view
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.session_turn_fixtures import TurnWorld, a_result, a_turn_world
from tests.unit.application.writer_fixtures import World, a_world, an_attempt
from tests.unit.fakes.skill_catalog import FakeSkillCatalog

PLAN = (("intake", "conversation"),)
ROW: dict[str, Any] = {
    "step": "intake",
    "skill": "bmad-prd",
    "persona": "Mary",
    "prompts": {"open": "Open the intake."},
}
PARK = Park(kind="conversation", reason="conversation · intake", path="intake")


def parked_result() -> StepResult:
    return StepResult(status="checkpoint", gate="human", reason=PARK.reason, park=PARK)


def world_of() -> World:
    world = a_world(
        "running",
        PLAN,
        {"intake": "running"},
        {"intake": dict(ROW)},
        inputs={"harness": "claude", "model": "claude-sonnet", "first_turn": "Hello"},
    )
    world.ports = replace(world.ports, engine=world.engine)
    return world


def test_the_park_opens_the_session_once_and_enqueues_its_first_turn() -> None:
    world = world_of()
    an_attempt(world, "intake")

    apply_step_result(world.ports, world.run.id, 1, parked_result())

    run = world.stored_run()
    assert (run.status, run.park_kind, run.senior_session) == ("needs_you", "conversation", True)
    (start,) = [r for r in world.records() if r.event == "session_start"]
    assert (start.actor, start.text) == ("machine", STARTED_TEXT)
    assert start.payload == {"scope": "step", "harness": "claude", "model": "claude-sonnet"}
    (turn,) = [a for a in world.attempts_of("intake") if a.role == "session"]
    row = world.row("intake")
    assert turn.status == "queued"
    assert turn.started_at is not None
    assert turn.message == conversation.first_turn(row, [row], run.inputs)
    assert world.engine.calls.count(("enqueue_session_turn", (run.id, turn.id))) == 1
    assert [c for c in world.engine.calls if c[0] == "enqueue_session_turn"] == [
        ("enqueue_session_turn", (run.id, turn.id))
    ]


def test_a_second_park_after_a_turn_adds_no_turn() -> None:
    world = world_of()
    an_attempt(world, "intake")
    apply_step_result(world.ports, world.run.id, 1, parked_result())
    (turn,) = [a for a in world.attempts_of("intake") if a.role == "session"]
    world.ports.attempts.update(
        turn.model_copy(update={"status": "done", "ended_at": turn.started_at})
    )
    world.ports.runs.update(world.stored_run().model_copy(update={"status": "running"}))
    world.ports.steps.update(world.row("intake").model_copy(update={"status": "running"}))
    world.engine.calls.clear()

    apply_step_result(world.ports, world.run.id, 1, parked_result())

    assert len([a for a in world.attempts_of("intake") if a.role == "session"]) == 1
    assert [c for c in world.engine.calls if c[0] == "enqueue_session_turn"] == []


def test_a_park_of_another_kind_opens_no_session() -> None:
    world = world_of()
    an_attempt(world, "intake")
    park = Park(kind="blocked", reason="stuck", path="intake")

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(status="blocked", gate="human", reason="stuck", park=park),
    )

    assert "session_start" not in world.events()
    assert [c for c in world.engine.calls if c[0] == "enqueue_session_turn"] == []


def test_a_conversation_result_that_does_not_park_the_run_opens_no_session() -> None:
    world = world_of()
    an_attempt(world, "intake")
    world.ports.runs.update(world.run.model_copy(update={"pause_requested": True}))

    apply_step_result(world.ports, world.run.id, 1, parked_result())

    assert world.stored_run().park_kind == "conversation"


def test_a_run_without_harness_or_model_records_none() -> None:
    world = a_world("running", PLAN, {"intake": "running"}, {"intake": dict(ROW)})
    row = world.row("intake")

    with world.ports.uow:
        turn = open_step_session(world.ports, world.run, [row], row)

    (start,) = [r for r in world.records() if r.event == "session_start"]
    assert start.payload == {"scope": "step", "harness": None, "model": None}
    assert turn is not None
    stored = world.ports.attempts.get(turn)
    assert stored is not None
    assert (stored.harness, stored.model, stored.n) == (None, None, 1)


def step_world(skill: str | None, catalog: FakeSkillCatalog | None) -> tuple[TurnWorld, Any, Any]:
    resolved = {**ROW, "skill": skill}
    if skill is None:
        del resolved["skill"]
    world = a_turn_world(
        results=[a_result(session_id="s-1")],
        with_resolved=resolved,
        start=False,
        plan=PLAN,
        park_path="intake",
        park_kind="conversation",
        row_status="checkpoint",
        inputs={"harness": "claude", "model": "claude-sonnet", "spec_folder": "specs/demo"},
    )
    writers = world.writers
    row = world.session.world.row("intake").model_copy(update={"with_resolved": resolved})
    writers.steps.update(row)
    with writers.uow:
        attempt_id = open_step_session(writers, world.session.world.stored_run(), [row], row)
        writers.uow.commit()
    assert attempt_id is not None
    ports = replace(world.ports, step=replace(world.step, skill_catalog=catalog))
    return world, ports, attempt_id


class Raising(FakeSkillCatalog):
    def installed_skills(self, harness: str) -> frozenset[str] | None:
        raise OSError("no manifest")


LISTED = FakeSkillCatalog({"claude": frozenset({"bmad-prd", "senior-session"})})


@pytest.mark.parametrize(
    ("skill", "catalog", "begins"),
    [
        ("bmad-prd", LISTED, "bmad-prd intake Mary\n"),
        ("skills/tech-lead/SKILL.md", LISTED, "skills/tech-lead/SKILL.md intake Mary\n"),
        (None, LISTED, "senior-session intake Mary\n"),
        ("bmad-prd", None, "bmad-prd intake Mary\n"),
        ("bmad-prd", Raising(), "bmad-prd intake Mary\n"),
    ],
)
def test_the_first_turn_opens_with_the_rows_skill(
    skill: str | None, catalog: FakeSkillCatalog | None, begins: str
) -> None:
    world, ports, attempt_id = step_world(skill, catalog)

    run_turn(ports, attempt_id)

    (start,) = world.harness.called("start")
    assert start["prompt"].startswith(begins)
    assert start["prompt"].endswith("\nOpen the intake.")


def test_an_unlisted_bare_name_fails_the_turn_without_starting_the_harness() -> None:
    catalog = FakeSkillCatalog({"claude": frozenset({"senior-session"})})
    world, ports, attempt_id = step_world("bmad-prd", catalog)

    run_turn(ports, attempt_id)

    assert world.harness.called("start") == []
    stored = world.attempt(attempt_id)
    assert stored.status == "error"
    assert stored.output_ref == (
        "skill bmad-prd is not installed on claude; name its repository path in with.skill"
    )


def test_the_session_view_reports_the_step_scope() -> None:
    world, _ports, _attempt = step_world("bmad-prd", None)

    view = session_view(
        SessionPorts(writers=world.writers, git=world.git), world.session.world.run.id
    )

    assert view.scope == "step"


def test_a_budget_park_on_top_opens_no_session() -> None:
    world = world_of()
    an_attempt(world, "intake")
    budget = Park(kind="budget", reason="over budget", path="intake")
    result = parked_result().model_copy(update={"budget_park": budget})

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        result,
        after_route=lambda run, row, res: budget_second_record(world.ports, run, row, res),
    )

    run = world.stored_run()
    assert (run.park_kind, run.senior_session) == ("budget", False)
    assert [r for r in world.records() if r.event == "session_start"] == []
    assert [a for a in world.attempts_of("intake") if a.role == "session"] == []
    assert [c for c in world.engine.calls if c[0] == "enqueue_session_turn"] == []
