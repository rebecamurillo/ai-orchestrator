"""Messages kept, cancel and forced skip mid-conversation (epic 4 story 5, AC1-AC3, AC5-AC7)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import (
    CONVERSATION_SESSION_SIGNALS,
    SENIOR_SESSION_SIGNALS,
    run_admitted_signals,
    validate,
)
from orchestrator.application.steps.context import StepPorts
from orchestrator.application.use_cases import conversation_effects, walk
from orchestrator.application.use_cases.conversation_session import open_step_session
from orchestrator.application.use_cases.session_turn import (
    SESSION_CLOSED,
    MessagePorts,
    post_message,
)
from orchestrator.application.use_cases.signal_effect import CancelPlan, Effect
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.application.use_cases.walk import WalkPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import WORKTREE
from tests.unit.application.session_turn_fixtures import a_turn_world
from tests.unit.application.writer_fixtures import World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

PLAN = (("plan", "plan.check"), ("talk", "conversation"), ("after", "shell"))
STOP = 3
INPUTS = {"harness": "claude", "model": "claude-sonnet"}


def talking(*, session_open: bool = True, turns: bool = True, **over: Any) -> World:
    """A Run parked `conversation` on `talk`, its session open with turn 1 `running`."""
    fields: dict[str, Any] = {
        "park_kind": "conversation",
        "park_path": "talk",
        "park_reason": "r",
        "park_seq": STOP,
        "inputs": INPUTS,
        **over,
    }
    world = a_world(
        "needs_you",
        PLAN,
        {"plan": "done", "talk": "checkpoint"},
        {"talk": {"step": "talk"}},
        **fields,
    )
    if session_open:
        row = world.row("talk")
        with world.ports.uow:
            opened = open_step_session(world.ports, world.run, [row], row)
            world.ports.uow.commit()
        assert opened is not None
        if turns:
            running = world.ports.attempts.get(opened)
            assert running is not None
            world.ports.attempts.update(
                running.model_copy(update={"status": "running", "pgid": 41})
            )
    return world


def session_turns(world: World) -> list[Attempt]:
    return [a for a in world.attempts_of("talk") if a.role == "session"]


def messages(world: World) -> MessagePorts:
    return MessagePorts(writers=world.ports, engine=world.engine)


def enqueued(world: World) -> list[UUID]:
    return [call[1][1] for call in world.engine.calls if call[0] == "enqueue_session_turn"]


def effect_ports(world: World, process: FakeProcessRunner, git: FakeGit) -> SignalEffectPorts:
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=git,
        process=process,
        work_dir="/work",
        read_environment=lambda _run_id: None,
    )


def with_queued(world: World) -> None:
    world.engine.calls.clear()
    post_message(messages(world), world.run.id, "second")
    post_message(messages(world), world.run.id, "third")


# AC1 ────────────────────────────────────────────────────────────────────────────────────


def test_a_message_during_a_running_turn_is_queued_and_enqueued_at_once() -> None:
    world = talking()
    world.engine.calls.clear()

    first = post_message(messages(world), world.run.id, "second")
    second = post_message(messages(world), world.run.id, "third")

    turns = session_turns(world)
    assert [t.n for t in turns] == [1, 2, 3]
    assert [t.status for t in turns] == ["running", "queued", "queued"]
    assert (first.attempt_id, second.attempt_id) == (turns[1].id, turns[2].id)
    assert enqueued(world) == [turns[1].id, turns[2].id]


def test_the_senior_session_keeps_its_409_while_a_turn_runs() -> None:
    world = talking(park_kind="blocked")
    world.engine.calls.clear()
    before = session_turns(world)

    with pytest.raises(Conflict, match="turn running"):
        post_message(messages(world), world.run.id, "hello")

    assert session_turns(world) == before
    assert enqueued(world) == []


# AC2 / AC3 ──────────────────────────────────────────────────────────────────────────────


def test_a_forced_skip_kills_the_turn_and_closes_the_queued_ones() -> None:
    world = talking()
    with_queued(world)
    process, git = FakeProcessRunner(), FakeGit()
    ports = effect_ports(world, process, git)

    handle_signal(
        ports, world.run.id, Signal(kind="skip_step", payload={"forced": True}, stop=STOP)
    )

    assert [c["pgid"] for c in process.called("kill_group")] == [41]
    _, second, third = session_turns(world)
    for turn, text in ((second, "second"), (third, "third")):
        assert (turn.status, turn.output_ref, turn.message) == ("error", "step skipped", text)
        assert turn.ended_at is not None
    run = world.stored_run()
    assert run.senior_session is False
    assert (world.status_of("talk"), world.row("talk").reason) == ("skipped", "skipped, forced")
    assert git.called("remove_worktree") == []
    assert git.called("delete_branch") == []


def test_cancel_kills_the_turn_and_closes_the_queued_ones() -> None:
    world = talking()
    with_queued(world)
    process = FakeProcessRunner()

    handle_signal(
        effect_ports(world, process, FakeGit()), world.run.id, Signal(kind="cancel", payload={})
    )

    assert [c["pgid"] for c in process.called("kill_group")] == [41]
    _, second, third = session_turns(world)
    assert [(t.status, t.output_ref) for t in (second, third)] == [("error", "Run cancelled")] * 2
    assert [t.message for t in (second, third)] == ["second", "third"]
    run = world.stored_run()
    assert (run.status, run.senior_session) == ("cancelled", False)


# AC5 ────────────────────────────────────────────────────────────────────────────────────


def test_open_turns_counts_running_session_attempts_without_ended_at() -> None:
    world = talking()
    row = world.row("talk")
    ended = Attempt(
        id=UUID(int=7),
        run_id=world.run.id,
        step_run_id=row.id,
        n=9,
        status="error",
        role="session",
        started_at=world.clock.now(),
        ended_at=world.clock.now(),
    )
    world.ports.attempts.add(ended)
    walk_ports = WalkPorts(
        writers=world.ports,
        step=StepPorts(
            git=FakeGit(), clock=world.clock, work_dir="/work", process=FakeProcessRunner()
        ),
    )

    assert walk.open_turns(walk_ports, world.run.id) == 1

    (running,) = [t for t in session_turns(world) if t.status == "running"]
    world.ports.attempts.update(running.model_copy(update={"ended_at": world.clock.now()}))
    assert walk.open_turns(walk_ports, world.run.id) == 0


# AC6 ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["session_end", "step_close", "cancel"])
def test_an_open_conversation_session_admits_its_own_signals(kind: str) -> None:
    world = talking()
    run, row = world.run.model_copy(update={"senior_session": True}), world.row("talk")

    rule = validate(run, row, Signal(kind=kind, payload={}, stop=STOP), [row])

    assert rule is not None
    assert kind in CONVERSATION_SESSION_SIGNALS


def test_an_open_conversation_session_admits_a_forced_skip() -> None:
    world = talking()
    run, row = world.run.model_copy(update={"senior_session": True}), world.row("talk")

    validate(run, row, Signal(kind="skip_step", payload={"forced": True}, stop=STOP), [row])

    with pytest.raises(Conflict, match="invalid for status"):
        validate(run, row, Signal(kind="skip_step", payload={}, stop=STOP), [row])


@pytest.mark.parametrize("kind", ["answer", "continue", "retry"])
def test_an_open_conversation_session_refuses_the_rest(kind: str) -> None:
    world = talking()
    run, row = world.run.model_copy(update={"senior_session": True}), world.row("talk")

    with pytest.raises(Conflict, match=f"senior session open: end it before {kind}"):
        validate(run, row, Signal(kind=kind, payload={}, stop=STOP), [row])


def test_the_conversation_session_offers_cancel_and_a_blocked_one_keeps_its_set() -> None:
    world = talking()
    run = world.run.model_copy(update={"senior_session": True})
    assert run_admitted_signals(run, "conversation") == ("cancel",)

    blocked = run.model_copy(update={"park_kind": "blocked"})
    assert run_admitted_signals(blocked, "agent") == SENIOR_SESSION_SIGNALS
    row = world.row("talk")
    with pytest.raises(Conflict, match="senior session open"):
        validate(blocked, row, Signal(kind="step_close", payload={}, stop=STOP), [row])


# AC7 ────────────────────────────────────────────────────────────────────────────────────


def test_a_message_after_session_end_reopens_the_step_session() -> None:
    world = talking(session_open=False)
    row = world.row("talk")
    with world.ports.uow:
        first = open_step_session(world.ports, world.run, [row], row)
        world.ports.uow.commit()
    assert first is not None
    done = world.ports.attempts.get(first)
    assert done is not None
    world.ports.attempts.update(
        done.model_copy(update={"status": "done", "ended_at": done.started_at})
    )
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": False}))
    world.clock.advance(1)
    world.engine.calls.clear()
    before = len([r for r in world.records() if r.event == "session_start"])

    posted = post_message(messages(world), world.run.id, "back again")

    starts = [r for r in world.records() if r.event == "session_start"]
    assert len(starts) == before + 1
    assert starts[-1].payload["scope"] == "step"
    assert world.stored_run().senior_session is True
    new = [t for t in session_turns(world) if t.id == posted.attempt_id]
    assert [t.status for t in new] == ["queued"]
    assert enqueued(world) == [posted.attempt_id]


def test_a_reopen_enqueues_the_opening_turn_first_when_the_row_had_none() -> None:
    world = talking(session_open=False)
    world.engine.calls.clear()

    posted = post_message(messages(world), world.run.id, "hello")

    opening, hers = sorted(session_turns(world), key=lambda t: t.n)
    assert hers.id == posted.attempt_id
    assert enqueued(world) == [opening.id, hers.id]


def test_a_message_with_no_session_and_no_conversation_stop_is_refused() -> None:
    world = a_world("needs_you", PLAN, {"talk": "blocked"}, park_kind="blocked", park_path="talk")

    with pytest.raises(Conflict, match="no senior session open"):
        post_message(messages(world), world.run.id, "hello")


# closing_turns ──────────────────────────────────────────────────────────────────────────


def _inner(plan: CancelPlan | None = None) -> Any:
    def effect(*_args: Any) -> Effect:
        return Effect(run_update={"x": 1}, cancel_plan=plan)

    return effect


def _call(world: World, effect: Any) -> Effect:
    run = world.stored_run()
    rows = world.ports.steps.list_for_run(run.id)
    return effect(world.ports, run, rows, world.row("talk"), Signal(kind="cancel", payload={}))


def test_closing_turns_returns_the_effect_unchanged_on_another_park() -> None:
    world = talking(park_kind="blocked")
    done = _call(world, conversation_effects.closing_turns(_inner(), "why"))

    assert done == Effect(run_update={"x": 1})


def test_closing_turns_returns_the_effect_unchanged_without_a_session() -> None:
    world = talking(session_open=False)
    done = _call(world, conversation_effects.closing_turns(_inner(), "why"))

    assert done == Effect(run_update={"x": 1})


def test_closing_turns_does_not_duplicate_a_pgid_the_effect_already_found() -> None:
    world = talking()
    inner = _inner(CancelPlan(pgids=(41, 5), worktrees=()))

    done = _call(world, conversation_effects.closing_turns(inner, "why"))

    assert done.cancel_plan == CancelPlan(pgids=(41, 5), worktrees=())
    assert done.run_update == {"x": 1, "senior_session": False}


def test_closing_turns_does_not_kill_a_running_turn_that_has_no_pgid() -> None:
    world = talking()
    (running,) = session_turns(world)
    world.ports.attempts.update(running.model_copy(update={"pgid": None}))

    done = _call(world, conversation_effects.closing_turns(_inner(), "why"))

    assert done.cancel_plan == CancelPlan(pgids=(), worktrees=())
    assert session.SESSION_ROLE == "session"


# a closed queued turn's own workflow ────────────────────────────────────────────────────


def test_the_commit_of_a_turn_closed_while_queued_keeps_it_as_closed() -> None:
    world = a_turn_world()
    posted = world.post()
    queued = world.attempt(posted.attempt_id)
    closed_at = world.session.world.clock.now()
    world.writers.attempts.mark_finished(
        queued.model_copy(
            update={"status": "error", "ended_at": closed_at, "output_ref": "step skipped"}
        )
    )
    world.session.world.clock.advance(5)
    world.workspace(WORKTREE).write(session.REPLY_FILE, "another turn's reply")

    world.run(posted.attempt_id)
    world.commit(posted.attempt_id)

    stored = world.attempt(posted.attempt_id)
    assert (stored.status, stored.output_ref, stored.ended_at) == (
        "error",
        "step skipped",
        closed_at,
    )
    assert stored.reply == ""
    assert world.spend_uows == []


def test_a_turn_killed_at_its_start_by_a_forced_skip_commits_no_tree() -> None:
    git = FakeGit(status=[" M next/row.py"] * 4)
    world = a_turn_world(git=git)
    turn = world.post()
    start = world.harness.start

    def skipped_first(**kwargs: Any) -> Any:
        run = world.session.world.stored_run()
        world.writers.runs.update(
            run.model_copy(update={"status": "running", "senior_session": False})
        )
        return start(**kwargs)

    world.harness.start = skipped_first  # type: ignore[method-assign]

    world.run(turn.attempt_id)
    world.commit(turn.attempt_id)

    assert world.process.called("kill_group") == [
        {"method": "kill_group", "pgid": world.harness.pgid}
    ]
    # the session's first turn sweeps before its start; no `session: turn` commit follows
    assert [message for _, message in git.called("commit")] == [session.WIP_MESSAGE]
    stored = world.attempt(turn.attempt_id)
    assert (stored.status, stored.output_ref) == ("error", SESSION_CLOSED)
    assert stored.ended_at is not None
