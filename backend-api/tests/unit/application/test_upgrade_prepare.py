"""`prepare_upgrade` (epic 9 story 3, AC1-AC3), on the shared fakes."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from orchestrator.application.use_cases import upgrade_prepare
from orchestrator.application.use_cases.upgrade_prepare import (
    NO_HOLD,
    PreparedConversation,
    UpgradePorts,
    prepare_upgrade,
)
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_transition_world import TransitionWorld
from tests.unit.application.test_initiative_reopen import cancels, conversation_row, parked_spec
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository


def hold_for(world: TransitionWorld, *, ttl: int = 600) -> FakeInstanceHoldRepository:
    now = world.harness.clock.now()
    return FakeInstanceHoldRepository(
        InstanceHold(id=new_id(), held_at=now, expires_at=now + timedelta(seconds=ttl), reason="up")
    )


def prepare(
    world: TransitionWorld, holds: FakeInstanceHoldRepository
) -> tuple[PreparedConversation, ...]:
    ports = UpgradePorts(initiative=world.ports, holds=holds)
    with world.uow:
        return prepare_upgrade(ports)


def parked_at(world: TransitionWorld, step: str, **fields: Any) -> Run:
    run = parked_spec(world, park_path="steps[1]", **fields)
    conversation_row(world, run, step, "running", 1)
    return run


def test_no_hold_refuses_and_changes_nothing() -> None:
    world = TransitionWorld()
    run = parked_at(world, "ux")

    for holds in (FakeInstanceHoldRepository(), hold_for(world, ttl=-1)):
        with pytest.raises(Conflict, match=NO_HOLD):
            prepare(world, holds)

    assert world.runs.runs[run.id].status == "needs_you"
    assert cancels(world) == []
    assert world.uow.rolled_back


@pytest.mark.parametrize(
    ("status", "park_kind"),
    [
        ("needs_you", "merge_conflict"),
        ("needs_you", "protected_path"),
        ("needs_you", "blocked"),
        ("queued", None),
        ("running", None),
    ],
)
def test_an_interactive_run_not_on_a_conversation_refuses_everything(
    status: str, park_kind: str | None
) -> None:
    world = TransitionWorld()
    spec = parked_at(world, "ux")
    merge = world.ended_run(1, status=status, park_kind=park_kind)

    with pytest.raises(Conflict) as refused:
        prepare(world, hold_for(world))

    text = str(refused.value)
    assert text.startswith(
        "upgrade-prepare refused: interactive Runs not parked on a conversation:"
    )
    assert f"{merge.id} ({status}/{park_kind or '-'})" in text
    assert world.runs.runs[spec.id].status == "needs_you"
    assert cancels(world) == []
    assert world.uow.rolled_back


def test_a_conversation_park_without_a_readable_step_refuses() -> None:
    world = TransitionWorld()
    run = parked_spec(world, park_path="steps[1]")

    with pytest.raises(Conflict, match=str(run.id)):
        prepare(world, hold_for(world))


def test_only_the_parked_conversation_is_cancelled() -> None:
    world = TransitionWorld()
    spec = parked_at(world, "ux")
    build = world.ended_run(2, status="needs_you", park_kind="blocked")
    other = build_run("needs_you", park_kind="checkpoint")
    world.runs.add(other)
    world.ended_run(0, status="done", round_=2)
    world.ended_run(1, status="cancelled")

    done = prepare(world, hold_for(world))

    assert done == (PreparedConversation(spec.id, world.initiative_row.id, "ux"),)
    assert world.runs.runs[spec.id].status == "cancelled"
    assert world.runs.runs[build.id].status == "needs_you"
    assert world.runs.runs[other.id].status == "needs_you"
    assert world.runs.runs[build.id].park_kind == "blocked"
    assert world.runs.runs[other.id].park_kind == "checkpoint"
    assert cancels(world) == [{"reason": "upgrade", "step": "ux"}]
    assert world.uow.committed


def test_two_conversations_are_listed_in_creation_order() -> None:
    world = TransitionWorld()
    first = parked_at(world, "product")
    world.another_initiative("second-one")
    second = world.ended_run(0, status="needs_you", park_kind="conversation", park_path="steps[1]")
    conversation_row(world, second, "tech", "running", 1)

    done = prepare(world, hold_for(world))

    assert [(p.run_id, p.step) for p in done] == [(first.id, "product"), (second.id, "tech")]
    assert len({p.initiative_id for p in done}) == len(done)


def test_a_run_that_ended_by_itself_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    world = TransitionWorld()
    parked_at(world, "ux")

    def gone(*_: Any, **__: Any) -> None:
        raise Conflict("ended")

    monkeypatch.setattr(upgrade_prepare, "handle_signal", gone)

    assert prepare(world, hold_for(world)) == ()


def test_a_run_at_a_position_the_sequence_lacks_is_ignored() -> None:
    world = TransitionWorld()
    world.runs.add(
        build_run(
            "needs_you",
            park_kind="blocked",
            initiative_id=world.initiative_row.id,
            initiative_round=1,
            initiative_position=9,
        )
    )

    assert prepare(world, hold_for(world)) == ()
