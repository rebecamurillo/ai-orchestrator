"""`read_activity` (SPEC CAP-3, AD-30): the working steps and the Runs the engine holds."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from orchestrator.application.preflight.checks import run_label
from orchestrator.application.use_cases.instance_activity import (
    ActivityPorts,
    EngineRun,
    WorkingStep,
    read_activity,
)
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=1)
T2 = T0 + timedelta(minutes=2)


class World:
    def __init__(self, version: str = "1") -> None:
        self.engine = FakeWorkflowEngine(clock=FakeClock(T0))
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.version = version

    def ports(self) -> ActivityPorts:
        return ActivityPorts(
            queue=QueuePorts(
                engine=self.engine,
                runs=self.runs,
                steps=self.steps,
                clock=FakeClock(T0),
                max_active_runs=2,
            ),
            attempts=self.attempts,
            dbos_application_version=self.version,
        )

    def run(self, status: str = "running", *, engine: bool = True, **over: object) -> Run:
        fields: dict[str, object] = {
            "id": new_id(),
            "project_id": new_id(),
            "repository_id": new_id(),
            "template_name": "epic",
            "template_version": 1,
            "status": status,
            "budget_usd": 0,
            "inputs": {"branch": "feat/x"},
            "created_at": T0,
        }
        fields.update(over)
        if engine:
            fields["engine_ref"] = {"ref": 1}
        run = Run(**fields)  # type: ignore[arg-type]
        self.runs.add(run)
        if engine and status in ("queued", "running", "needs_you"):
            self.engine.enqueue(run.id, "p")
        return run

    def row(self, run: Run, seq: int, status: str, kind: str = "shell") -> StepRun:
        row = StepRun(  # type: ignore[call-arg]
            id=new_id(),
            run_id=run.id,
            seq=seq,
            path=f"steps[{seq}]",
            label="x",
            kind=kind,
            gate="deterministic",
            status=status,  # type: ignore[arg-type]
        )
        self.steps.add_many([row])
        return row

    def attempt(self, row: StepRun, role: str = "agent", **over: object) -> Attempt:
        fields: dict[str, object] = {
            "id": new_id(),
            "run_id": row.run_id,
            "step_run_id": row.id,
            "n": 1,
            "role": role,
            "status": "running",
        }
        fields.update(over)
        attempt = Attempt(**fields)  # type: ignore[arg-type]
        self.attempts.add(attempt)
        return attempt


def test_working_steps_and_a_parked_run_in_the_engine() -> None:
    world = World()
    run_a = world.run()
    row_a = world.row(run_a, 1, "running")
    world.attempt(row_a, started_at=T1)
    run_b = world.run("needs_you", park_kind="checkpoint", park_path="steps[2]")
    row_b = world.row(run_b, 2, "checkpoint", kind="agent")
    world.attempt(row_b, "session", status="queued", started_at=T2)

    activity = read_activity(world.ports())

    assert activity.working == [
        WorkingStep(run_a.id, run_label(run_a), "steps[1]", "shell", T1),
        WorkingStep(run_b.id, run_label(run_b), "steps[2]", "session", T2),
    ]
    assert [r for r in activity.in_engine if r.run_id == run_b.id] == [
        EngineRun(run_b.id, run_label(run_b), "needs_you", "checkpoint", "waiting for your answer")
    ]
    assert activity.hold is None
    assert activity.dbos_application_version == "1"


def test_only_runs_held_by_the_engine_are_listed() -> None:
    world = World("2")
    blocked = world.run("needs_you", park_kind="blocked")
    queued = world.run("queued")
    world.run("queued", engine=False)
    for status in ("done", "failed", "cancelled"):
        world.run(status)

    activity = read_activity(world.ports())

    assert {r.run_id for r in activity.in_engine} == {blocked.id, queued.id}
    reasons = {r.run_id: r.queue_reason for r in activity.in_engine}
    assert reasons[blocked.id] == "waiting for your answer"
    assert reasons[queued.id] is not None
    assert activity.working == []
    assert activity.dbos_application_version == "2"


def test_a_run_in_the_engine_without_a_queue_row_has_no_reason() -> None:
    world = World()
    run = world.run("running")
    del world.engine.queue[run.id]

    [engine_run] = read_activity(world.ports()).in_engine

    assert engine_run.queue_reason is None


def test_in_engine_is_ordered_by_creation() -> None:
    world = World()
    later = world.run(created_at=T2)
    earlier = world.run("needs_you", created_at=T1)

    assert [r.run_id for r in read_activity(world.ports()).in_engine] == [earlier.id, later.id]


def test_a_consult_on_a_running_row_is_one_entry() -> None:
    world = World()
    run = world.run()
    row = world.row(run, 1, "running", kind="agent")
    world.attempt(row, started_at=T1)
    world.attempt(row, "consult", n=2, started_at=T2)

    [step] = read_activity(world.ports()).working

    assert (step.kind, step.started_at) == ("consult", T2)


def test_a_running_row_without_an_open_attempt_has_no_start() -> None:
    world = World()
    run = world.run()
    row = world.row(run, 1, "running")
    world.attempt(row, ended_at=T1, status="done")

    [step] = read_activity(world.ports()).working

    assert (step.kind, step.started_at) == ("shell", None)


def test_an_unstarted_session_turn_is_listed_without_a_start() -> None:
    world = World()
    run = world.run("needs_you")
    row = world.row(run, 1, "blocked", kind="agent")
    world.attempt(row, "session", status="queued")

    [step] = read_activity(world.ports()).working

    assert (step.kind, step.started_at, step.path) == ("session", None, "steps[1]")


def test_closed_attempts_and_open_agent_attempts_on_idle_rows_list_nothing() -> None:
    world = World()
    run = world.run()
    row = world.row(run, 1, "done")
    world.attempt(row, "session", ended_at=T1, status="done")
    world.attempt(row, "consult", n=2, ended_at=T1, status="done")
    world.attempt(row, "agent", n=3)

    assert read_activity(world.ports()).working == []


def test_a_gone_run_or_row_is_skipped() -> None:
    world = World()
    run = world.run()
    row = world.row(run, 1, "running")
    ghost = world.run(engine=False)
    ghost_row = world.row(ghost, 1, "running")
    del world.runs.runs[ghost.id]
    orphan_turn = Attempt(
        id=new_id(), run_id=run.id, step_run_id=new_id(), n=1, role="session", status="queued"
    )
    world.attempts.add(orphan_turn)
    gone_run_turn = Attempt(
        id=new_id(), run_id=new_id(), step_run_id=ghost_row.id, n=2, role="session", status="queued"
    )
    world.attempts.add(gone_run_turn)

    paths = [(s.run_id, s.path) for s in read_activity(world.ports()).working]

    assert paths == [(run.id, row.path)]


def test_working_steps_order_by_start_then_path() -> None:
    world = World()
    run = world.run()
    unstarted = world.row(run, 1, "running")
    second = world.row(run, 3, "running")
    first = world.row(run, 2, "running")
    world.attempt(second, started_at=T1)
    world.attempt(first, started_at=T1)

    paths: list[str] = [s.path for s in read_activity(world.ports()).working]

    assert paths == [first.path, second.path, unstarted.path]
    assert isinstance(run.id, UUID)
