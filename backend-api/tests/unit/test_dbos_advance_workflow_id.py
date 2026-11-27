"""The advance workflow receives its own workflow id, `{advance_id}:{hex}`: the facade starts
`workflow(id)` under that id (`DbosDurableEngine.enqueue`), and `enqueue_advance` makes it fresh
on every call. Release review 2026-11-26: every advance raised on `UUID('{id}:{hex}')`."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.dbos import advance as module
from orchestrator.infrastructure.dbos.advance import build_advance
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.test_dbos_advance import _scope, an_engine, deps_for


def test_the_step_reads_the_advance_id_out_of_the_workflow_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[UUID] = []
    monkeypatch.setattr(module, "advance_initiative", lambda _ports, id_: seen.append(id_))
    advance_id = new_id()

    build_advance(FakeDurableEngine(), deps_for(_scope))(f"{advance_id}:{uuid4().hex}")  # type: ignore[arg-type]

    assert seen == [advance_id]


def test_the_id_the_engine_enqueues_is_one_the_step_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[UUID] = []
    monkeypatch.setattr(module, "advance_initiative", lambda _ports, id_: seen.append(id_))
    fake = FakeDurableEngine()
    engine = an_engine(fake, _scope)
    engine.launch()
    advance_id = new_id()

    engine.enqueue_advance(advance_id)
    [(_, workflow_id, _)] = fake.enqueued
    build_advance(FakeDurableEngine(), deps_for(_scope))(workflow_id)  # type: ignore[arg-type]

    assert seen == [advance_id]
