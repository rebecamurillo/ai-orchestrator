"""The start-up sweep of initiative advances (epic 8 story 1, AC16)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial

import pytest

from orchestrator.application.use_cases.initiative_advance import AdvancePorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.dbos import startup as startup_module
from orchestrator.infrastructure.dbos.advance_ports import open_advance_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.application.test_initiative_advance import Case
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.dbos import FakeDurableEngine, a_queued_workflow
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.test_dbos_advance import an_engine


@contextmanager
def _writer_scope(*_a: object, **_k: object) -> Iterator[object]:
    yield object()


def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup_module, "sweep_dependency_waiting", lambda *_a: None)
    monkeypatch.setattr(startup_module, "sweep_session_turns", lambda *_a: None)
    monkeypatch.setattr(startup_module, "open_writer_ports", _writer_scope)


def test_only_the_unheld_unblocked_advance_is_enqueued(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    case = Case()
    held = case.advance
    free = held.model_copy(update={"id": new_id(), "position": 2})
    blocked = held.model_copy(update={"id": new_id(), "position": 3, "blocked_reason": "x"})
    case.world.advances.add(free)
    case.world.advances.add(blocked)

    @contextmanager
    def scope() -> Iterator[AdvancePorts]:
        yield case.ports

    fake = FakeDurableEngine(queued=[a_queued_workflow(f"{held.id}:ab", "PENDING", EPOCH)])
    engine = an_engine(fake, scope)
    recorder = FakeWorkflowEngine()
    _quiet(monkeypatch)
    monkeypatch.setattr(engine, "enqueue_advance", recorder.enqueue_advance)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert recorder.calls == [("enqueue_advance", free.id)]


def test_without_the_advance_scope_none_is_swept(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    engine = an_engine(FakeDurableEngine())
    recorder = FakeWorkflowEngine()
    _quiet(monkeypatch)
    monkeypatch.setattr(engine, "enqueue_advance", recorder.enqueue_advance)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert recorder.calls == []


def test_the_walker_deps_wire_the_advance_scope(env: dict[str, str]) -> None:
    deps = startup_module.walker_deps(Settings(), lambda: None, FakeGit(), engine_ref=[])  # type: ignore[arg-type]

    assert isinstance(deps.advance_writes, partial)
    assert deps.advance_writes.func is open_advance_ports
