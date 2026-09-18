"""`_do_sweep_dependency_residue` (story 5-4): startup crash-residue recovery.

On container restart, a Run that had its predecessor land `done` but whose `engine_ref`
was never written (crash between `engine.enqueue` and the second UoW commit) is re-enqueued
here.  The function lives in `infrastructure/dbos/startup.py`, guarded by `_SERVING`; this
test calls the private inner function directly, patching `open_writer_ports` with fakes.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.infrastructure.dbos.startup import _do_sweep_dependency_residue
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

_PATCH_TARGET = "orchestrator.infrastructure.dbos.startup.open_writer_ports"


def _shared_ports(runs: FakeRunRepository) -> WriterPorts:
    return WriterPorts(
        runs=runs,
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=FakeUnitOfWork(),
        clock=FakeClock(),
    )


def _patched_open(runs: FakeRunRepository):
    """Return a patch-compatible context manager that always yields from the shared runs."""

    @contextmanager
    def _open(_session_factory):
        yield _shared_ports(runs)

    return _open


def test_sweep_enqueues_crash_residue_dependent() -> None:
    """A queued Run with after_run_id → done predecessor and engine_ref={} is enqueued."""
    predecessor = build_run(status="done")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    runs = FakeRunRepository([predecessor, dependent])
    engine = FakeWorkflowEngine()

    with patch(_PATCH_TARGET, _patched_open(runs)):
        _do_sweep_dependency_residue(engine, None)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert len(enqueue_calls) == 1


def test_sweep_writes_engine_ref_and_clears_after_run_id() -> None:
    """After enqueue, engine_ref is written and after_run_id is cleared on the dependent."""
    predecessor = build_run(status="done")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    runs = FakeRunRepository([predecessor, dependent])
    engine = FakeWorkflowEngine()

    with patch(_PATCH_TARGET, _patched_open(runs)):
        _do_sweep_dependency_residue(engine, None)

    stored = runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref  # truthy — non-empty dict written by enqueue
    assert stored.after_run_id is None


def test_sweep_ignores_run_with_pending_predecessor() -> None:
    """A dependent whose predecessor is still running is not enqueued."""
    predecessor = build_run(status="running")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    runs = FakeRunRepository([predecessor, dependent])
    engine = FakeWorkflowEngine()

    with patch(_PATCH_TARGET, _patched_open(runs)):
        _do_sweep_dependency_residue(engine, None)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert enqueue_calls == []


def test_sweep_ignores_already_enqueued_dependent() -> None:
    """A dependent that already has engine_ref (successfully enqueued earlier) is not touched."""
    predecessor = build_run(status="done")
    already_enqueued = build_run(
        status="queued", after_run_id=predecessor.id, engine_ref={"dbos_id": "existing"}
    )
    runs = FakeRunRepository([predecessor, already_enqueued])
    engine = FakeWorkflowEngine()

    with patch(_PATCH_TARGET, _patched_open(runs)):
        _do_sweep_dependency_residue(engine, None)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert enqueue_calls == []


def test_sweep_is_noop_when_no_queued_dependents() -> None:
    """No queued runs → no engine calls."""
    predecessor = build_run(status="done")
    runs = FakeRunRepository([predecessor])
    engine = FakeWorkflowEngine()

    with patch(_PATCH_TARGET, _patched_open(runs)):
        _do_sweep_dependency_residue(engine, None)

    assert engine.calls == []
