"""The `conversation` executor's first execute and the rows it ends (epic 4 story 3, AC4)."""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.steps.conversation import ConversationExecutor
from orchestrator.application.use_cases import walk_context
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import World, a_world, an_attempt, build_run
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

PLAN = (("intake", "conversation"), ("product", "conversation"), ("ux", "conversation"))
STEPS = ("intake", "product", "ux")


def world_of(**inputs: Any) -> World:
    return a_world(
        "running",
        PLAN,
        {"intake": "running", "product": "planned", "ux": "planned"},
        {name: {"step": name} for name in STEPS},
        inputs=inputs,
    )


def context_of(world: World, path: str, *, resume: GateRecord | None = None) -> StepContext:
    row = world.row(path)
    attempt = an_attempt(world, path)
    environment = RunEnvironment(
        run_id=world.run.id,
        project_slug="acme",
        repository_slug="widgets",
        repository_url="https://github.com/acme/widgets.git",
        default_branch="main",
        bmad_version="6.11.0",
        spec_folder=None,
        run=world.run,
        plan_rows=tuple(world.ports.steps.list_for_run(world.run.id)),
    )
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=None,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=attempt,
        resume_signal=resume,
        ports=StepPorts(
            git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work", run_env=environment
        ),
    )


def test_a_first_execute_parks_the_run_on_the_conversation() -> None:
    world = world_of()

    result = ConversationExecutor().execute(context_of(world, "intake"))

    assert result.status == "checkpoint"
    assert result.reason == "conversation · intake"
    assert result.park is not None
    assert (result.park.kind, result.park.reason, result.park.path) == (
        "conversation",
        "conversation · intake",
        "intake",
    )


def test_a_row_outside_the_round_is_skipped() -> None:
    world = world_of(round_steps="ux,tech")

    skipped = ConversationExecutor().execute(context_of(world, "product"))
    parked = ConversationExecutor().execute(context_of(world, "ux"))

    assert (skipped.status, skipped.reason, skipped.park) == ("skipped", "not in this round", None)
    assert parked.status == "checkpoint"
    assert parked.park is not None
    assert parked.park.kind == "conversation"


def test_a_round_naming_no_conversation_step_is_a_misconfigured_error() -> None:
    world = world_of(round_steps="design")

    result = ConversationExecutor().execute(context_of(world, "intake"))

    assert result.status == "error"
    assert result.reason == "round_steps design names no conversation step"
    assert result.park is not None
    assert (result.park.kind, result.park.reason, result.park.path) == (
        "misconfigured",
        "round_steps design names no conversation step",
        "intake",
    )


def test_a_resumed_execute_returns_the_same_park() -> None:
    world = world_of(round_steps="ux")
    record = GateRecord(
        id=new_id(),
        run_id=world.run.id,
        event="answer",
        actor="operator",
        at=EPOCH,
    )

    result = ConversationExecutor().execute(context_of(world, "ux", resume=record))

    assert result.status == "checkpoint"
    assert result.park is not None
    assert (result.park.kind, result.park.path) == ("conversation", "ux")


def test_a_skipped_result_ends_the_row_skipped_and_queues_the_next() -> None:
    world = world_of(round_steps="ux")
    result = ConversationExecutor().execute(context_of(world, "intake"))
    assert result.status == "skipped"

    apply_step_result(world.ports, world.run.id, world.row("intake").seq, result)

    assert world.status_of("intake") == "skipped"
    assert world.row("intake").reason == "not in this round"
    assert world.status_of("product") == "queued"
    assert world.stored_run().status == "running"


def test_plan_rows_are_filled_for_a_conversation_row_only() -> None:
    world = a_world(
        "running",
        (("sync", "git.sync"), ("intake", "conversation")),
        {"sync": "running", "intake": "running"},
    )
    an_attempt(world, "sync")
    an_attempt(world, "intake")
    base = RunEnvironment(
        run_id=world.run.id,
        project_slug="acme",
        repository_slug="widgets",
        repository_url="u",
        default_branch="main",
        bmad_version="6.11.0",
        spec_folder=None,
    )
    ports = StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work", run_env=base)
    run: Run = world.run

    talk = walk_context.context(world.ports, ports, run, world.row("intake").seq, None)
    other = walk_context.context(world.ports, ports, run, world.row("sync").seq, None)

    assert talk.ports.run_env is not None
    assert [row.path for row in talk.ports.run_env.plan_rows] == ["sync", "intake"]
    assert other.ports.run_env is not None
    assert other.ports.run_env.plan_rows == ()
    assert isinstance(talk.ports.run_env.plan_rows[0], StepRun)
    assert build_run is not None
