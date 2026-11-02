"""`pause_stop`: the park a pause lands as, and the test for "this record resumed a pause".

A `continue` that resumed a pause is not the `continue` that approves a spec checkpoint or a
stale plan, so the row that runs next must not be handed it as a resume signal."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.pause_stop import (
    PAUSED_REASON,
    park_paused,
    resumed_a_pause,
)
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.walk import (
    WalkPorts,
    close_run,
    expire,
    next_row,
    run_row,
)
from orchestrator.application.use_cases.writers import Entry, record
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
DONE = StepResult(status="done", gate="deterministic")


def line(event: str, **over: object) -> GateRecord:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "at": EPOCH,
        "event": event,
        "actor": "operator",
        "text": "",
    }
    fields.update(over)
    return GateRecord(**fields)  # type: ignore[arg-type]


# ── resumed_a_pause ──────────────────────────────────────────────────────────


def test_a_continue_after_a_pause_resumed_it() -> None:
    park, resume = line("paused", actor="machine"), line("continue")

    assert resumed_a_pause([park, resume], resume)


def test_records_between_the_pause_and_the_continue_do_not_hide_it() -> None:
    park, edit, resume = line("paused", actor="machine"), line("spec_edit"), line("continue")

    assert resumed_a_pause([park, edit, resume], resume)


def test_a_continue_after_any_other_stop_did_not() -> None:
    park, resume = line("checkpoint", actor="machine"), line("continue")

    assert not resumed_a_pause([park, resume], resume)


def test_the_stop_that_counts_is_the_latest_one_before_the_record() -> None:
    paused, later, resume = line("paused"), line("plan_stale"), line("continue")

    assert not resumed_a_pause([paused, later, resume], resume)


def test_a_record_with_no_stop_before_it_resumed_nothing() -> None:
    resume = line("continue")

    assert not resumed_a_pause([line("start"), resume], resume)


def test_a_later_stop_is_not_the_one_the_record_answered() -> None:
    resume, later = line("continue"), line("paused")

    assert not resumed_a_pause([resume, later], resume)


# ── park_paused ──────────────────────────────────────────────────────────────


def test_park_paused_names_the_row_it_waits_before() -> None:
    world = a_world("running", EPIC_PLAN, {VERIFY: "queued"}, pause_requested=True)

    parked = park_paused(world.ports, world.stored_run(), VERIFY)

    assert (parked.status, parked.park_kind, parked.park_path) == ("needs_you", "paused", VERIFY)
    assert parked.park_reason == PAUSED_REASON.format(path=VERIFY)
    assert parked.pause_requested is False
    assert world.stored_run() == parked


# ── the row after a pause runs as a first dispatch ───────────────────────────


class Recording:
    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def agent() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("agent", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def ports(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )


def paused_before_an_agent_row() -> World:
    plan = (("plan", "plan.check"), (BUILD, "agent"))
    world = a_world("running", plan, {"plan": "running"}, pause_requested=True)
    an_attempt(world, "plan")
    apply_step_result(world.ports, world.run.id, 1, DONE)
    assert world.stored_run().park_path == BUILD
    return world


def test_the_row_after_a_pause_is_handed_no_resume_signal(agent: Recording) -> None:
    world = paused_before_an_agent_row()
    # an older approval of some other stop is still in the Run's history
    record(world.ports, world.stored_run(), Entry(event="continue", actor="operator", path="x"))
    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))
    seq = next_row(ports(world), world.run.id)
    assert seq == world.row(BUILD).seq
    an_attempt(world, BUILD)

    run_row(ports(world), world.run.id, world.row(BUILD).seq, "continue")

    [ctx] = agent.seen
    assert ctx.resume_signal is None


def test_a_continue_that_approved_another_stop_still_resumes_its_row(agent: Recording) -> None:
    plan = (("plan", "plan.check"), (BUILD, "agent"))
    world = a_world(
        "needs_you",
        plan,
        {BUILD: "checkpoint"},
        park_kind="checkpoint",
        park_path=BUILD,
        park_reason="spec",
    )
    record(world.ports, world.stored_run(), Entry(event="checkpoint", actor="machine", path=BUILD))
    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))
    an_attempt(world, BUILD, n=2)

    run_row(ports(world), world.run.id, world.row(BUILD).seq, "continue")

    [ctx] = agent.seen
    assert ctx.resume_signal is not None and ctx.resume_signal.event == "continue"


# ── the walk around a pause ──────────────────────────────────────────────────


def test_a_paused_run_is_not_closed_as_stalled() -> None:
    world = paused_before_an_agent_row()

    assert close_run(ports(world), world.run.id) == "needs_you"
    assert world.stored_run().park_kind == "paused"


def test_a_pause_expires_after_thirty_days_like_any_other_stop() -> None:
    world = paused_before_an_agent_row()

    assert expire(ports(world), world.run.id) == "failed"
    assert world.events()[-1] == "failed"
    assert world.stored_run().park_kind is None
