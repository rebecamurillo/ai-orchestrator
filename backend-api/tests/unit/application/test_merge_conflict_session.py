"""A merge conflict opens a conversation with the merge agent (epic 8 story 4, AC1, AC2 rule,
AC6, AC10, AC11)."""

from __future__ import annotations

import pytest

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import (
    INVALID,
    MERGE_SESSION_SIGNALS,
    admitted_signals,
    run_admitted_signals,
)
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.merge_world import (
    AGENT,
    MERGE,
    SKILL,
    a_merge_world,
    a_parked_merge_world,
)
from tests.unit.application.writer_fixtures import World


def pending_turn(world: World) -> None:
    (turn,) = [a for a in world.attempts_of(MERGE) if a.role == "session"]
    assert turn.status == "queued"


def finish_turn(world: World) -> None:
    for turn in [a for a in world.attempts_of(MERGE) if a.role == "session"]:
        world.ports.attempts.update(
            turn.model_copy(update={"status": "done", "ended_at": world.clock.now()})
        )


def enqueued(world: World) -> list[object]:
    return [c for c in world.engine.calls if c[0] == "enqueue_session_turn"]


def test_an_initiative_merge_conflict_opens_a_step_session_with_its_first_turn() -> None:
    world = a_parked_merge_world()

    run = world.stored_run()
    assert (run.status, run.park_kind, run.senior_session) == (
        "needs_you",
        "merge_conflict",
        True,
    )
    (start,) = [r for r in world.records() if r.event == "session_start"]
    assert start.payload["scope"] == "step"
    pending_turn(world)
    assert len(enqueued(world)) == 1


def test_a_run_without_an_initiative_opens_no_session_and_refuses_continue() -> None:
    world = a_parked_merge_world(initiative=False)

    assert "session_start" not in world.events()
    assert enqueued(world) == []
    assert world.stored_run().senior_session is False
    with pytest.raises(Conflict) as refused:
        signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))
    assert str(refused.value) == INVALID.format(
        kind="continue", status="needs_you", park="merge_conflict"
    )


def test_the_stop_offers_todays_signals_whatever_the_run() -> None:
    assert admitted_signals("merge_conflict", "git.merge") == ("retry", "skip_step", "cancel")
    world = a_parked_merge_world(initiative=False)
    assert "continue" not in run_admitted_signals(world.stored_run(), world.row(MERGE))


def test_retry_and_cancel_are_admitted_with_no_session_open() -> None:
    world = a_parked_merge_world()
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": False}))

    outcome = signal_run(world.signal_ports, world.run.id, Signal(kind="retry"))

    assert outcome.run.status == "running"
    assert "session_end" not in world.events()


def test_cancel_is_admitted_with_no_session_open() -> None:
    world = a_parked_merge_world()
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": False}))

    assert signal_run(world.signal_ports, world.run.id, Signal(kind="cancel")).run.status == (
        "cancelled"
    )


@pytest.mark.parametrize("kind", ["continue", "retry"])
def test_an_answer_ends_the_open_session_before_its_own_record(kind: str) -> None:
    world = a_parked_merge_world()
    finish_turn(world)

    outcome = signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind=kind),
        actor="operator",  # type: ignore[arg-type]
    )

    events = world.events()
    assert events.index("session_end") < events.index(kind)
    ended = next(r for r in world.records() if r.event == "session_end")
    assert ended.actor == "operator"
    assert outcome.run.senior_session is False
    assert world.stored_run().senior_session is False


@pytest.mark.parametrize("kind", ["continue", "retry"])
def test_a_turn_still_pending_refuses_the_answer_and_writes_nothing(kind: str) -> None:
    world = a_parked_merge_world()
    before = world.events()

    with pytest.raises(Conflict, match="turn running"):
        signal_run(world.signal_ports, world.run.id, Signal(kind=kind))  # type: ignore[arg-type]

    assert world.events() == before
    assert world.stored_run().senior_session is True
    assert world.stored_run().status == "needs_you"


def test_the_open_session_admits_the_merge_signals_and_refuses_the_rest() -> None:
    world = a_parked_merge_world()
    run = world.stored_run()

    assert session.merge_session(run)
    assert MERGE_SESSION_SIGNALS == ("cancel", "session_end", "continue", "retry")
    with pytest.raises(Conflict, match="senior session open"):
        signal_run(world.signal_ports, run.id, Signal(kind="skip_step"))


def test_the_machine_actor_and_text_override_the_tables() -> None:
    world = a_parked_merge_world()
    finish_turn(world)

    signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind="continue"),
        actor="machine",
        text="merge resumed after the agent's turn",
    )

    record = next(r for r in world.records() if r.event == "continue")
    assert (record.actor, record.text) == ("machine", "merge resumed after the agent's turn")
    ended = next(r for r in world.records() if r.event == "session_end")
    assert ended.actor == "machine"


def test_the_rules_over_the_parked_run() -> None:
    world = a_parked_merge_world()
    run = world.stored_run()
    merge = world.row(MERGE)
    rows = world.ports.steps.list_for_run(run.id)

    assert session.opens_step_session(run, "merge_conflict")
    assert not session.opens_step_session(run, "blocked")
    assert not session.opens_step_session(run, "conversation")
    assert session.parked_skill(merge, rows) == SKILL
    assert session.parked_skill(world.row(AGENT), rows) == SKILL


def test_the_skill_is_that_of_the_last_agent_row_before_the_merge_in_its_frame() -> None:
    world = a_merge_world()
    merge = world.row(MERGE).model_copy(update={"seq": 10})
    agent = world.row(AGENT)

    def agent_at(seq: int, skill: str, frame: str | None = agent.frame) -> StepRun:
        return agent.model_copy(
            update={"id": new_id(), "seq": seq, "frame": frame, "with_resolved": {"skill": skill}}
        )

    rows = [
        agent_at(2, "first"),
        agent_at(7, "last"),
        agent_at(8, "other-frame", "epics[1]"),
        agent_at(11, "after-the-merge"),
    ]

    assert session.parked_skill(merge, rows) == "last"
    assert session.parked_skill(merge, rows[:1]) == "first"
    assert session.parked_skill(merge, [rows[0], rows[2], rows[3]]) == "first"
    assert session.parked_skill(merge, rows[2:]) is None


def test_no_agent_row_or_no_skill_leaves_the_opening_skill() -> None:
    world = a_merge_world(skill=None)
    rows = world.ports.steps.list_for_run(world.run.id)
    merge = world.row(MERGE)

    assert session.parked_skill(merge, rows) is None
    assert session.parked_skill(merge, [merge]) is None
    assert session.step_skill_ref(session.parked_skill(merge, rows), None) == session.OPENING_SKILL
