"""`infrastructure/dbos/advance.py` and the adapter side of it (epic 8 story 1, AC14-AC17)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.use_cases.initiative_advance import AdvancePorts
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.infrastructure.dbos import advance as module
from orchestrator.infrastructure.dbos.adapter import NOT_LAUNCHED, DbosWorkflowEngine
from orchestrator.infrastructure.dbos.advance import NOT_WIRED, build_advance
from orchestrator.infrastructure.dbos.config import SESSION_QUEUE, EngineConfig
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from orchestrator.infrastructure.engine.local import LocalWorkflowEngine
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.dbos import FakeDurableEngine, a_queued_workflow
from tests.unit.fakes.engine import FakeWorkflowEngine


def deps_for(scope: Any = None) -> WalkerDeps:
    return WalkerDeps(
        open_ports=lambda: None,  # type: ignore[arg-type, return-value]
        step_ports=None,  # type: ignore[arg-type]
        human_wait_seconds=5,
        advance_writes=scope,
    )


def an_engine(fake: FakeDurableEngine, scope: Any = None) -> DbosWorkflowEngine:
    config = EngineConfig(
        database_url="postgresql+psycopg://user:pw@postgres:5432/orchestrator",
        application_version="1",
        max_active_runs=3,
    )
    return DbosWorkflowEngine(config, fake, deps_for(scope))


@contextmanager
def _scope() -> Iterator[AdvancePorts]:
    yield None  # type: ignore[misc]


def test_the_advance_is_one_workflow_of_one_step() -> None:
    fake = FakeDurableEngine()

    build_advance(fake, deps_for(_scope))  # type: ignore[arg-type]

    assert fake.declared == [("step", "advance_run"), ("workflow", "run_initiative_advance")]


def test_the_step_runs_advance_initiative_through_the_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[object, UUID]] = []
    monkeypatch.setattr(module, "advance_initiative", lambda ports, id_: seen.append((ports, id_)))
    advance_id = new_id()

    build_advance(FakeDurableEngine(), deps_for(_scope))(str(advance_id))  # type: ignore[arg-type]

    assert seen == [(None, advance_id)]


def test_without_the_scope_the_step_says_it_is_not_wired() -> None:
    workflow = build_advance(FakeDurableEngine(), deps_for())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match=NOT_WIRED):
        workflow(str(new_id()))


def test_ac14_each_enqueue_is_a_fresh_workflow_under_the_advance_partition() -> None:
    fake = FakeDurableEngine()
    engine = an_engine(fake, _scope)
    engine.launch()
    advance_id = new_id()

    engine.enqueue_advance(advance_id)
    engine.enqueue_advance(advance_id)

    [(q1, w1, p1), (q2, w2, p2)] = fake.enqueued
    assert q1 == q2 == SESSION_QUEUE
    assert w1.startswith(f"{advance_id}:") and w2.startswith(f"{advance_id}:") and w1 != w2
    assert p1 == p2 == str(advance_id)


def test_ac14_held_advances_read_the_colon_ids_and_the_other_holds_skip_them() -> None:
    advance_id, turn, calculation = new_id(), new_id(), new_id()
    fake = FakeDurableEngine(
        queued=[
            a_queued_workflow(f"{advance_id}:abc", "PENDING", EPOCH),
            a_queued_workflow(str(turn), "PENDING", EPOCH),
            a_queued_workflow(str(calculation), "ENQUEUED", EPOCH),
        ]
    )
    engine = an_engine(fake, _scope)

    assert engine.held_advances() == frozenset({advance_id})
    assert advance_id not in engine.held_calculations()
    assert advance_id not in engine.held_session_turns()
    assert engine.held_calculations() == frozenset({turn, calculation})


def test_ac15_an_advance_enqueued_before_the_launch_is_a_bug_and_says_so() -> None:
    with pytest.raises(RuntimeError, match=NOT_LAUNCHED):
        an_engine(FakeDurableEngine(), _scope).enqueue_advance(new_id())


def test_the_workflow_is_declared_at_launch_only_when_the_scope_is_wired() -> None:
    wired, unwired = FakeDurableEngine(), FakeDurableEngine()

    an_engine(wired, _scope).launch()
    an_engine(unwired).launch()

    assert ("workflow", "run_initiative_advance") in wired.declared
    assert ("workflow", "run_initiative_advance") not in unwired.declared
    names = [name for name, _ in wired.calls]
    assert names.index("workflow") < names.index("start")
    with pytest.raises(RuntimeError, match=NOT_LAUNCHED):
        an_engine(unwired).enqueue_advance(new_id())


def test_ac17_every_engine_satisfies_the_port() -> None:
    assert isinstance(LocalWorkflowEngine(), WorkflowEngine)
    assert isinstance(FakeWorkflowEngine(), WorkflowEngine)
    assert isinstance(an_engine(FakeDurableEngine()), WorkflowEngine)
