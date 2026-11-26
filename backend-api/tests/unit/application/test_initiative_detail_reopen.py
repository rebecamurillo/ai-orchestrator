"""The detail of a build a reopen cancelled (epic 9 story 2, AC4's detail half)."""

from __future__ import annotations

from typing import Literal

import pytest

from orchestrator.application.use_cases.initiative_views import initiative_detail
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.initiative import FrozenSequence
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import ReadWorld, sequence
from tests.unit.initiative_fixtures import AT

LINE = "stopped on the spec · intake reopens"
BUILD = 2


def as_step(seq: FrozenSequence) -> FrozenSequence:
    build = seq.workflows[BUILD].model_copy(update={"shown_as": "step"})
    return seq.model_copy(update={"workflows": (*seq.workflows[:BUILD], build)})


def reopened(world: ReadWorld, seq: FrozenSequence, spec_status: str, branch: str = "created"):  # type: ignore[no-untyped-def]
    initiative = world.initiative(round=2, sequence=seq)
    build = world.run(initiative, position=BUILD, status="cancelled", template_name="p/build")
    world.records.add(
        GateRecord(
            id=new_id(),
            run_id=build.id,
            at=AT,
            event="cancel",
            actor="operator",
            payload={"reason": "reopen", "step": "intake", "branch": branch},
        )
    )
    world.run(initiative, position=0, initiative_round=2, status=spec_status, minutes=5)
    world.row(world.runs.list_for_initiative(initiative.id)[-1], 1, status="running")
    return initiative


@pytest.mark.parametrize("branch", ["created", "attached"])
def test_a_shown_build_reads_blk_and_the_reopened_step_names_it(
    branch: Literal["created", "attached"],
) -> None:
    world = ReadWorld()
    initiative = reopened(world, sequence(), "needs_you", branch)

    detail = initiative_detail(world.ports, initiative.id)

    build = detail.workflows[-1]
    assert (build.workflow, build.token, build.line) == ("build", "BLK", LINE)
    intake = detail.workflows[0].steps[0]
    assert intake.reopened_after is not None
    assert (intake.reopened_after.workflow, intake.reopened_after.branch) == ("build", branch)
    assert detail.workflows[0].token is None


def test_a_build_shown_as_a_step_reads_blk_and_the_line() -> None:
    world = ReadWorld()
    initiative = reopened(world, as_step(sequence()), "running")

    detail = initiative_detail(world.ports, initiative.id)

    step = next(s for s in detail.workflows[0].steps if s.id == "build")
    assert (step.token, step.line) == ("BLK", LINE)
    assert detail.workflows[0].steps[0].reopened_after is not None


@pytest.mark.parametrize("shown", ["workflow", "step"])
def test_a_done_spec_round_clears_the_mark(shown: str) -> None:
    world = ReadWorld()
    seq = sequence() if shown == "workflow" else as_step(sequence())
    initiative = reopened(world, seq, "done")

    detail = initiative_detail(world.ports, initiative.id)

    assert all(w.token is None for w in detail.workflows)
    assert all(s.reopened_after is None for w in detail.workflows for s in w.steps)
    assert all(LINE not in w.line for w in detail.workflows)
    assert all(LINE not in s.line for w in detail.workflows for s in w.steps)
