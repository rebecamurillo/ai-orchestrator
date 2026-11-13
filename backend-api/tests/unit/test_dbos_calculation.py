"""`infrastructure/dbos/calculation.py` and the adapter's side of it (epic 2 story 5, AD-6).

The calculation is its own workflow on the session queue, declared before `start`, with its
own two steps; the walk's and the session turn's declarations are untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial

import pytest

from orchestrator.application.use_cases.calculate_metrics import CalculationPorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.dbos import calculation as module
from orchestrator.infrastructure.dbos import startup as startup_module
from orchestrator.infrastructure.dbos.adapter import NOT_LAUNCHED, DbosWorkflowEngine
from orchestrator.infrastructure.dbos.calculation import NOT_WIRED, build_calculation
from orchestrator.infrastructure.dbos.config import SESSION_QUEUE, EngineConfig
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from orchestrator.infrastructure.engine.local import LocalWorkflowEngine
from orchestrator.infrastructure.settings import Settings
from tests.unit.application.test_calculate_metrics_job import Job, a_job
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.dbos import FakeDurableEngine, a_queued_workflow
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit

TWO = 2


def deps_for(job: Job | None, sleeps: list[float] | None = None) -> WalkerDeps:
    @contextmanager
    def scope() -> Iterator[CalculationPorts]:
        assert job is not None
        yield job.ports

    return WalkerDeps(
        open_ports=lambda: None,  # type: ignore[arg-type, return-value]
        step_ports=None,  # type: ignore[arg-type]
        human_wait_seconds=5,
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
        calculation_writes=scope if job is not None else None,
    )


def an_engine(fake: FakeDurableEngine, job: Job | None = None) -> DbosWorkflowEngine:
    config = EngineConfig(
        database_url="postgresql+psycopg://user:pw@postgres:5432/orchestrator",
        application_version="1",
        max_active_runs=3,
    )
    return DbosWorkflowEngine(config, fake, deps_for(job))


def test_the_calculation_is_one_workflow_of_two_steps() -> None:
    engine = FakeDurableEngine()

    build_calculation(engine, deps_for(None))

    assert engine.declared == [
        ("step", "calculation_wait"),
        ("step", "calculation_run"),
        ("workflow", "run_metrics_calculation"),
    ]


def test_the_workflow_waits_then_writes_a_version() -> None:
    job = a_job()
    calculation_id = job.queue()
    workflow = build_calculation(FakeDurableEngine(), deps_for(job))

    workflow(str(calculation_id))

    assert job.calculations.get(calculation_id).state == "done"  # type: ignore[union-attr]
    assert len(job.versions.versions) == 1


def test_a_held_or_waiting_calculation_sleeps_and_asks_again() -> None:
    job = a_job()
    calculation_id = job.queue()
    sleeps: list[float] = []
    outcomes = iter(["held", "waiting", "started"])

    original = module.begin_calculation
    module.begin_calculation = lambda ports, cid: (  # type: ignore[assignment]
        original(ports, cid) if (o := next(outcomes)) == "started" else o  # type: ignore[arg-type, return-value]
    )
    try:
        workflow = build_calculation(FakeDurableEngine(), deps_for(job, sleeps))
        workflow(str(calculation_id))
    finally:
        module.begin_calculation = original

    assert len(sleeps) == TWO
    assert job.calculations.get(calculation_id).state == "done"  # type: ignore[union-attr]


def test_a_wait_step_that_raises_fails_the_calculation_instead_of_leaving_it_queued() -> None:
    job = a_job()
    calculation_id = job.queue()

    def boom(_ports: object, _cid: object) -> str:
        raise RuntimeError("lost connection")

    original = module.begin_calculation
    module.begin_calculation = boom  # type: ignore[assignment]
    try:
        build_calculation(FakeDurableEngine(), deps_for(job))(str(calculation_id))
    finally:
        module.begin_calculation = original

    failed = job.calculations.get(calculation_id)
    assert failed is not None
    assert (failed.state, failed.output) == ("failed", "RuntimeError: lost connection")
    assert job.versions.versions == []


def test_a_replayed_calculation_does_nothing_twice() -> None:
    job = a_job()
    calculation_id = job.calculate()
    workflow = build_calculation(FakeDurableEngine(), deps_for(job))

    workflow(str(calculation_id))

    assert len(job.versions.versions) == 1


def test_a_missing_scope_is_a_wiring_bug_raised_when_a_step_runs() -> None:
    workflow = build_calculation(FakeDurableEngine(), deps_for(None))

    with pytest.raises(RuntimeError, match=NOT_WIRED):
        workflow(str(new_id()))


def test_launching_declares_the_workflow_before_start_and_adds_no_queue() -> None:
    fake = FakeDurableEngine()

    an_engine(fake).launch()

    assert fake.calls.index(("workflow", "run_metrics_calculation")) < fake.calls.index(
        ("start", None)
    )
    assert [a for n, a in fake.calls if n == "register_queue"][-1][0] == SESSION_QUEUE
    assert len([1 for n, _ in fake.calls if n == "register_queue"]) == TWO


def test_a_calculation_is_enqueued_on_the_session_queue_under_its_own_id() -> None:
    fake = FakeDurableEngine()
    engine = an_engine(fake)
    engine.launch()
    calculation_id = new_id()

    assert engine.enqueue_calculation(calculation_id) is None

    assert fake.enqueued == [(SESSION_QUEUE, str(calculation_id), str(calculation_id))]


def test_a_calculation_enqueued_before_the_launch_is_a_bug_and_says_so() -> None:
    with pytest.raises(RuntimeError, match=NOT_LAUNCHED):
        an_engine(FakeDurableEngine()).enqueue_calculation(new_id())


def test_the_adapter_names_the_calculations_the_session_queue_holds() -> None:
    held = new_id()
    fake = FakeDurableEngine(queued=[a_queued_workflow(str(held), "PENDING", EPOCH)])

    assert an_engine(fake).held_calculations() == frozenset({held})
    assert ("queued", SESSION_QUEUE) in fake.calls


def test_the_local_engine_takes_a_calculation_and_runs_nothing() -> None:
    assert LocalWorkflowEngine().enqueue_calculation(new_id()) is None


def test_the_walker_deps_wire_the_calculation_scope(env: dict[str, str]) -> None:
    deps = startup_module.walker_deps(Settings(), lambda: None, FakeGit())  # type: ignore[arg-type]

    assert isinstance(deps.calculation_writes, partial)
    assert deps.calculation_writes.func is startup_module.open_calculation_ports


def test_the_startup_sweep_fails_a_calculation_the_engine_lost_and_requeues_a_queued_one(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    job = a_job()
    lost = job.queue(1, "running")
    waiting = job.queue(2, "queued")
    engine = an_engine(FakeDurableEngine(), job)
    recorder = FakeWorkflowEngine()
    monkeypatch.setattr(startup_module, "sweep_dependency_waiting", lambda *_a: None)
    monkeypatch.setattr(startup_module, "sweep_session_turns", lambda *_a: None)
    monkeypatch.setattr(startup_module, "open_writer_ports", _writer_scope)
    monkeypatch.setattr(engine, "enqueue_calculation", recorder.enqueue_calculation)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    failed = job.calculations.get(lost)
    assert failed is not None and (failed.state, failed.output) == ("failed", "interrupted")
    assert job.versions.versions == []
    assert recorder.calls == [("enqueue_calculation", waiting)]


@contextmanager
def _writer_scope(*_a: object, **_k: object) -> Iterator[object]:
    yield object()


def test_a_process_without_a_calculation_scope_sweeps_none(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    engine = an_engine(FakeDurableEngine())
    monkeypatch.setattr(startup_module, "sweep_dependency_waiting", lambda *_a: None)
    monkeypatch.setattr(startup_module, "sweep_session_turns", lambda *_a: None)
    monkeypatch.setattr(startup_module, "open_writer_ports", _writer_scope)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())
