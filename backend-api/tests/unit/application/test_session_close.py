"""The attestation of a conversation step session's turn (epic 5 story 1, 2026-11-23, AC1-AC8).

A step closes only when the agent writes this very turn's attempt id to `CLOSE_FILE` and the
turn ended `done` with no later message pending; every other attestation is removed with one
`close_discarded` record. Shared fakes only (AD-18).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
import structlog

from orchestrator.application.rules import session
from orchestrator.application.use_cases import session_close
from orchestrator.application.use_cases.session_turn import commit_turn
from orchestrator.application.use_cases.signal_apply import SignalPorts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import BUILD
from tests.unit.application.session_turn_fixtures import TurnWorld, a_result, a_turn_world
from tests.unit.fakes.workspace import FakeWorkspace

ROW_PATH = BUILD
CLOSE = "attest with {attempt_id}"
ROW: dict[str, Any] = {
    "harness": "claude",
    "model": "claude-sonnet",
    "step": "intake",
    "prompts": {"open": "Open the intake.", "close": CLOSE},
}


def a_conversation(**over: Any) -> TurnWorld:
    """One conversation row parked at `park_seq` 5, its step session open."""
    fields: dict[str, Any] = {
        "plan": ((ROW_PATH, "conversation"),),
        "park_kind": "conversation",
        "row_status": "checkpoint",
        "park_seq": 5,
        "senior_session": True,
        "with_resolved": dict(ROW),
        "start": False,
    }
    fields.update(over)
    world = a_turn_world(**fields)
    inner = world.session.world
    inner.ports.records.add(
        GateRecord(
            id=new_id(),
            run_id=inner.run.id,
            at=inner.clock.now(),
            event="session_start",
            actor="machine",
            payload={"scope": "step", "harness": "claude", "model": "claude-sonnet"},
        )
    )
    return world


def tree(world: TurnWorld) -> FakeWorkspace:
    return world.workspace()


def close_records(world: TurnWorld) -> list[GateRecord]:
    return [r for r in world.session.world.records() if r.event == "close_discarded"]


def sent(world: TurnWorld) -> list[GateRecord]:
    return [r for r in world.session.world.records() if r.event == "step_close"]


def turn_run(world: TurnWorld, text: str = "ok") -> UUID:
    """One message posted and dispatched; its commit is the test's to run."""
    posted = world.post(text)
    world.run(posted.attempt_id)
    return posted.attempt_id


def ports_with_signal(world: TurnWorld) -> Any:
    inner = world.session.world
    return replace(world.ports, signal=SignalPorts(writers=inner.ports, engine=inner.engine))


def commit_signalled(world: TurnWorld, attempt_id: UUID, attestation: str | None) -> None:
    if attestation is not None:
        tree(world).write(session.CLOSE_FILE, attestation)
    commit_turn(ports_with_signal(world), attempt_id)


def a_world_of_results(n: int = 3) -> TurnWorld:
    return a_conversation(results=[a_result(session_id="s-1") for _ in range(n)])


def test_a_stale_attestation_is_gone_before_the_harness_starts() -> None:
    world = a_world_of_results()
    tree(world).write(session.CLOSE_FILE, "an earlier turn")
    seen: list[bool] = []
    world.harness.on_wait = lambda: seen.append(tree(world).exists(session.CLOSE_FILE))

    turn_run(world)

    assert seen == [False]


def test_the_harness_gets_the_message_and_the_close_instruction_naming_the_turn() -> None:
    world = a_world_of_results()
    first = turn_run(world, "hello")
    world.commit(first)

    second = turn_run(world, "ok")

    resumed = world.harness.called("start_resume")[0]
    assert resumed["message"] == f"ok\n\nattest with {second}"
    assert world.attempt(second).message == "ok"
    opening = world.harness.called("start")[0]["prompt"]
    assert opening.endswith(f"hello\n\nattest with {first}")
    assert world.attempt(first).message == "hello"


def test_an_attestation_of_an_earlier_turn_is_discarded() -> None:
    world = a_world_of_results()
    first = turn_run(world, "one")
    world.commit(first)
    second = turn_run(world, "two")

    commit_signalled(world, second, str(first))

    assert not tree(world).exists(session.CLOSE_FILE)
    (record,) = close_records(world)
    assert (record.actor, record.text) == ("machine", f"close discarded: attempt {first}")
    assert sent(world) == []
    assert world.session.world.stored_run().park_kind == "conversation"


def test_a_foreign_attestation_is_repeated_bounded_and_without_nul() -> None:
    world = a_world_of_results()
    turn = turn_run(world)

    commit_signalled(world, turn, "a\x00" + "b" * 500)

    (record,) = close_records(world)
    echoed = "a" + "b" * 500
    assert record.text == f"close discarded: attempt {echoed[: session_close.ECHO_LIMIT]}"
    assert sent(world) == []


def test_an_attestation_with_a_later_message_queued_is_deferred() -> None:
    world = a_world_of_results()
    first = turn_run(world, "one")
    world.commit(first)
    second = turn_run(world, "two")
    world.post("three")

    commit_signalled(world, second, str(second))

    assert not tree(world).exists(session.CLOSE_FILE)
    (record,) = close_records(world)
    assert record.text == "close deferred: later message"
    assert sent(world) == []


def test_an_attestation_of_the_last_turn_closes_the_step_once() -> None:
    world = a_world_of_results()
    first = turn_run(world, "one")
    world.commit(first)
    third = turn_run(world, "three")

    commit_signalled(world, third, f"{third}\n")

    inner = world.session.world
    assert not tree(world).exists(session.CLOSE_FILE)
    (closed,) = sent(world)
    assert closed.text == "step closed"
    assert closed.payload.get("attempt_id") == str(third)
    assert inner.row(ROW_PATH).status == "queued"
    assert close_records(world) == []
    assert len([c for c in inner.engine.calls if c[0] == "signal"]) == 1


def test_a_step_file_alone_closes_nothing() -> None:
    world = a_world_of_results()
    third = turn_run(world)
    tree(world).write("stories/1.md", "status: final")
    before = len(world.session.world.records())

    commit_signalled(world, third, None)

    assert len(world.session.world.records()) == before
    assert sent(world) == []


def test_an_attestation_on_a_failed_turn_is_discarded() -> None:
    world = a_conversation(results=[a_result(exit_code=1)])
    turn = turn_run(world)

    commit_signalled(world, turn, str(turn))

    assert not tree(world).exists(session.CLOSE_FILE)
    (record,) = close_records(world)
    assert record.text == "close discarded: turn failed"
    assert sent(world) == []


def test_a_run_parked_on_another_stop_reads_nothing() -> None:
    world = a_turn_world()
    posted = world.post()
    world.run(posted.attempt_id)
    seen: list[str] = []
    tree(world).read_lenient = seen.append  # type: ignore[method-assign,assignment]
    before = len(world.session.world.records())

    session_close.after_turn(ports_with_signal(world), posted.attempt_id)

    assert seen == []
    assert len(world.session.world.records()) == before
    assert sent(world) == []


def test_a_turn_end_without_signal_ports_sends_nothing_and_says_so() -> None:
    world = a_world_of_results()
    turn = turn_run(world)
    tree(world).write(session.CLOSE_FILE, str(turn))

    with structlog.testing.capture_logs() as logs:
        world.commit(turn)

    assert [entry["event"] for entry in logs if entry["log_level"] == "warning"] == [
        session_close.NOT_WIRED
    ]
    assert not tree(world).exists(session.CLOSE_FILE)
    assert sent(world) == []


def test_a_refused_signal_is_logged_not_raised_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = a_world_of_results()
    turn = turn_run(world)
    tree(world).write(session.CLOSE_FILE, str(turn))
    original = session_close.signal_run
    calls: list[Signal] = []

    def stale(signal_ports: SignalPorts, run_id: UUID, signal: Signal) -> Any:
        calls.append(signal)
        return original(signal_ports, run_id, Signal(kind=signal.kind, stop=1))

    monkeypatch.setattr(session_close, "signal_run", stale)

    with structlog.testing.capture_logs() as logs:
        commit_turn(ports_with_signal(world), turn)

    assert len(calls) == 1
    assert [e["event"] for e in logs if e["log_level"] == "warning"] == [session_close.REFUSED]
    assert sent(world) == []


def test_a_link_at_the_attestation_is_removed_and_nothing_is_written() -> None:
    world = a_world_of_results()
    turn = turn_run(world)
    tree(world).write(session.CLOSE_FILE, str(turn))
    tree(world).links.add(session.CLOSE_FILE)
    before = len(world.session.world.records())

    session_close.after_turn(ports_with_signal(world), turn)

    assert not tree(world).exists(session.CLOSE_FILE)
    assert session.CLOSE_FILE not in tree(world).links
    assert len(world.session.world.records()) == before
    assert sent(world) == []
