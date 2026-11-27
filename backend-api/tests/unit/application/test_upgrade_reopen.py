"""`reopen_after_upgrade` (epic 9 story 3, AC4-AC6), on the shared fakes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from orchestrator.application.use_cases import upgrade_reopen
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.application.use_cases.upgrade_prepare import UpgradePorts, prepare_upgrade
from orchestrator.application.use_cases.upgrade_reopen import UPGRADE_TURN, reopen_after_upgrade
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.initiative_transition_world import TransitionWorld
from tests.unit.application.test_initiative_reopen import conversation_row, parked_spec
from tests.unit.application.test_upgrade_prepare import hold_for

ROUND_TWO = 2


def parked_at(world: TransitionWorld, step: str, done: tuple[str, ...] = ()) -> Run:
    run = parked_spec(world, park_path="steps[9]")
    for seq, name in enumerate(done, start=1):
        conversation_row(world, run, name, "done", seq)
    conversation_row(world, run, step, "running", 9)
    return run


def upgrade(world: TransitionWorld) -> None:
    with world.uow:
        prepare_upgrade(UpgradePorts(initiative=world.ports, holds=hold_for(world)))


def after_upgrade(world: TransitionWorld) -> tuple[object, ...]:
    with world.uow:
        return reopen_after_upgrade(world.ports)


def test_the_cancelled_conversation_reopens_once() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    old = parked_at(world, "ux")
    upgrade(world)

    assert after_upgrade(world) == (world.initiative_row.id,)

    assert world.initiatives.initiatives[world.initiative_row.id].round == ROUND_TWO
    fresh = [r for r in world.runs.runs.values() if r.id != old.id]
    assert len(fresh) == 1
    assert fresh[0].inputs["round_steps"] == "ux,tech"
    assert fresh[0].inputs["first_turn"] == UPGRADE_TURN
    assert UPGRADE_TURN.startswith("instance upgraded: this step reopens here.")

    assert after_upgrade(world) == ()
    assert len(world.runs.runs) == ROUND_TWO


def test_done_steps_are_not_replayed() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    parked_at(world, "ux", done=("intake", "product"))
    upgrade(world)

    after_upgrade(world)

    fresh = [r for r in world.runs.runs.values() if r.status != "cancelled"]
    assert fresh[0].inputs["round_steps"] == "ux,tech"


def test_an_operator_cancel_or_a_live_run_is_left_alone() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    run = parked_at(world, "ux")
    with world.uow:
        handle_signal(world.ports.signals, run.id, Signal(kind="cancel"))

    assert after_upgrade(world) == ()

    other = TransitionWorld()
    parked_at(other, "ux")
    assert after_upgrade(other) == ()


def test_a_closed_initiative_is_left_alone() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    parked_at(world, "ux")
    upgrade(world)
    row = world.initiatives.initiatives[world.initiative_row.id]
    world.initiatives.initiatives[row.id] = row.model_copy(
        update={"cancelled_at": world.harness.clock.now()}
    )

    assert after_upgrade(world) == ()


def test_a_failing_reopen_is_logged_and_the_next_still_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = TransitionWorld()
    first = world.initiative_row
    parked_at(world, "ux")
    world.another_initiative("second-one")
    world.spec_branch(epics=False)
    second = world.ended_run(0, status="needs_you", park_kind="conversation", park_path="steps[9]")
    conversation_row(world, second, "tech", "running", 9)
    upgrade(world)
    real = upgrade_reopen.reopen_initiative

    def flaky(ports: Any, initiative_id: UUID, step: str, reason: str) -> Run:
        if initiative_id == first.id:
            raise Conflict("hub is unreachable")
        return real(ports, initiative_id, step, reason)

    monkeypatch.setattr(upgrade_reopen, "reopen_initiative", flaky)

    with capture_logs() as logs:
        reopened = after_upgrade(world)

    failed = [e for e in logs if e["event"] == "upgrade_reopen_failed"]
    assert [e["initiative_id"] for e in failed] == [str(first.id)]
    assert reopened == (world.initiative_row.id,)


def test_a_cancelled_run_without_a_cancel_record_is_left_alone() -> None:
    world = TransitionWorld()
    world.ended_run(0, status="cancelled")

    assert after_upgrade(world) == ()
