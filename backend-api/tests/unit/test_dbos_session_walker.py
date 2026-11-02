"""`infrastructure/dbos/session_walker.py` and the adapter's session queue (story 2-5, AD-6,
AD-23).

A turn is its own workflow, outside the walk: `run_session_turn(attempt_id)` calls two
steps, `session_turn` then `session_commit`, and the commit runs even when the turn's step
raised. Its workflow id is the attempt id, its queue `sessions`, its partition the Run. A
recovered turn left `running` by a crash is killed, closed, billed and committed, so the
session can end again.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.session_turn import INTERRUPTED
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.infrastructure.dbos import startup as startup_module
from orchestrator.infrastructure.dbos.adapter import NOT_LAUNCHED, DbosWorkflowEngine
from orchestrator.infrastructure.dbos.config import QUEUE_NAME, SESSION_QUEUE, EngineConfig
from orchestrator.infrastructure.dbos.session_walker import build_session_turn
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from orchestrator.infrastructure.engine.local import LocalWorkflowEngine
from orchestrator.infrastructure.settings import Settings
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world
from tests.unit.fakes.dbos import FakeDurableEngine

CONCURRENCY = 3
COST = Decimal("0.250000")


def deps_for(world: TurnWorld) -> WalkerDeps:
    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.writers

    return WalkerDeps(
        open_ports=open_ports,
        step_ports=world.step,
        human_wait_seconds=5,
        read_environment=world._environment,
    )


def an_engine(fake: FakeDurableEngine, world: TurnWorld | None = None) -> DbosWorkflowEngine:
    config = EngineConfig(
        database_url="postgresql+psycopg://user:pw@postgres:5432/orchestrator",
        application_version="1",
        max_active_runs=CONCURRENCY,
    )
    return DbosWorkflowEngine(config, fake, deps_for(world or a_turn_world()))


def test_the_turn_is_one_workflow_of_two_steps() -> None:
    engine = FakeDurableEngine()

    build_session_turn(engine, deps_for(a_turn_world()))

    assert engine.declared == [
        ("step", "session_turn"),
        ("step", "session_commit"),
        ("workflow", "run_session_turn"),
    ]


def test_a_turn_runs_and_is_committed() -> None:
    world = a_turn_world()
    posted = world.post()
    turn = build_session_turn(FakeDurableEngine(), deps_for(world))

    turn(str(posted.attempt_id))

    stored = world.attempt(posted.attempt_id)
    assert stored.status == "done"
    assert stored.ended_at is not None
    assert len(world.harness.called("start")) == 1


def test_the_commit_runs_even_when_the_turn_step_raises() -> None:
    world = a_turn_world()
    posted = world.post()
    deps = deps_for(world)
    opened: list[str] = []

    @contextmanager
    def counting() -> Iterator[WriterPorts]:
        opened.append("open")
        yield world.writers

    turn = build_session_turn(
        FakeDurableEngine(),
        WalkerDeps(
            open_ports=counting,
            step_ports=deps.step_ports,
            human_wait_seconds=5,
            read_environment=_failing_once(deps),
        ),
    )

    with pytest.raises(RuntimeError, match="db gone"):
        turn(str(posted.attempt_id))

    assert opened == ["open", "open"]
    assert world.harness.calls == []
    assert world.attempt(posted.attempt_id).ended_at is not None


def _failing_once(deps: WalkerDeps):  # type: ignore[no-untyped-def]
    seen: list[UUID] = []

    def read(run_id: UUID):  # type: ignore[no-untyped-def]
        seen.append(run_id)
        if len(seen) == 1:
            raise RuntimeError("db gone")
        assert deps.read_environment is not None
        return deps.read_environment(run_id)

    return read


def test_a_turn_a_crash_left_running_is_recovered_and_the_session_can_end() -> None:
    world = a_turn_world()
    crashed = world.session.turn(1, status="running", ended_at=None, pgid=917, start_sha="a" * 40)
    world.gateway.script(
        world.session.world.run.id,
        crashed.id,
        AttemptSpend(usd=COST, tokens_in=1, tokens_out=1, by_model=(), calls=1, provisional=False),
    )
    turn = build_session_turn(FakeDurableEngine(), deps_for(world))

    turn(str(crashed.id))

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 917}]
    assert world.harness.calls == []
    stored = world.attempt(crashed.id)
    assert (stored.status, stored.output_ref) == ("error", INTERRUPTED)
    assert stored.ended_at is not None
    assert world.session.world.stored_run().spend_usd == COST
    world.session.send("session_end")
    assert world.session.world.stored_run().senior_session is False


def test_launching_declares_the_session_queue_after_the_runs_queue() -> None:
    fake = FakeDurableEngine()

    an_engine(fake).launch()

    queues = [args for name, args in fake.calls if name == "register_queue"]
    assert queues == [(QUEUE_NAME, CONCURRENCY), (SESSION_QUEUE, CONCURRENCY)]
    assert SESSION_QUEUE == "sessions"
    assert ("workflow", "run_session_turn") in fake.declared


def test_a_turn_is_enqueued_under_its_attempt_id_behind_its_run() -> None:
    fake = FakeDurableEngine()
    engine = an_engine(fake)
    engine.launch()
    run_id, attempt_id = new_id(), new_id()

    assert engine.enqueue_session_turn(run_id, attempt_id) is None

    assert fake.enqueued == [(SESSION_QUEUE, str(attempt_id), str(run_id))]


def test_a_turn_enqueued_before_the_launch_is_a_bug_and_says_so() -> None:
    engine = an_engine(FakeDurableEngine())

    with pytest.raises(RuntimeError, match=NOT_LAUNCHED):
        engine.enqueue_session_turn(new_id(), new_id())


def test_the_local_engine_takes_a_turn_and_runs_nothing() -> None:
    assert LocalWorkflowEngine().enqueue_session_turn(new_id(), new_id()) is None


def test_the_startup_sweep_runs_the_session_sweep_after_the_dependency_sweep(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    order: list[str] = []
    world = a_turn_world()

    @contextmanager
    def ports(*_args: object, **_kwargs: object) -> Iterator[WriterPorts]:
        yield world.writers

    monkeypatch.setattr(startup_module, "open_writer_ports", ports)
    monkeypatch.setattr(
        startup_module, "sweep_dependency_waiting", lambda *_a: order.append("dependency")
    )
    monkeypatch.setattr(startup_module, "sweep_session_turns", lambda *_a: order.append("session"))
    engine = an_engine(FakeDurableEngine(), world)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert order == ["dependency", "session"]
