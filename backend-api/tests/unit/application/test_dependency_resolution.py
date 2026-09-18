"""`resolve_for_done` and `resolve_for_failed_or_cancelled` (story 5-4, AD-8).

Unit coverage for every branch in `resolve_dependents.py`:
- `resolve_for_done`: returns saved dependents; ignores non-matching and already-enqueued runs.
- `resolve_for_failed_or_cancelled`: parks dependents with `park_kind="dependency"` and writes
  a gate record; ignores already-enqueued dependents.
"""

from __future__ import annotations

from orchestrator.application.use_cases.resolve_dependents import (
    REASON_DEPENDENCY_ENDED,
    resolve_for_done,
    resolve_for_failed_or_cancelled,
)
from orchestrator.application.use_cases.writers import WriterPorts
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)


def _make_ports(runs: list) -> WriterPorts:
    """Minimal WriterPorts for dependency resolution tests (no engine needed)."""
    return WriterPorts(
        runs=FakeRunRepository(runs),
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=FakeUnitOfWork(),
        clock=FakeClock(),
    )


# ── resolve_for_done ─────────────────────────────────────────────────────────


def test_resolve_for_done_returns_saved_dependents() -> None:
    """A queued run with after_run_id pointing at the done predecessor is returned."""
    predecessor = build_run(status="done")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    ports = _make_ports([predecessor, dependent])

    result = resolve_for_done(ports, predecessor)

    assert len(result) == 1
    assert result[0].id == dependent.id


def test_resolve_for_done_ignores_runs_with_different_after_run_id() -> None:
    """A queued run waiting for a different run is not returned."""
    predecessor = build_run(status="done")
    other = build_run(status="done")
    waiting_for_other = build_run(status="queued", after_run_id=other.id, engine_ref={})
    ports = _make_ports([predecessor, waiting_for_other])

    result = resolve_for_done(ports, predecessor)

    assert result == []


def test_resolve_for_done_ignores_already_enqueued_dependents() -> None:
    """A run that already has an engine_ref (already enqueued) is not returned."""
    predecessor = build_run(status="done")
    already_enqueued = build_run(
        status="queued", after_run_id=predecessor.id, engine_ref={"ref": 42}
    )
    ports = _make_ports([predecessor, already_enqueued])

    result = resolve_for_done(ports, predecessor)

    assert result == []


def test_resolve_for_done_returns_empty_when_no_dependents() -> None:
    """No queued dependents → empty list."""
    predecessor = build_run(status="done")
    ports = _make_ports([predecessor])

    result = resolve_for_done(ports, predecessor)

    assert result == []


# ── resolve_for_failed_or_cancelled ─────────────────────────────────────────


def test_resolve_for_failed_parks_dependent_as_dependency() -> None:
    """A failed predecessor parks its saved dependent with park_kind='dependency'."""
    predecessor = build_run(status="failed")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    ports = _make_ports([predecessor, dependent])

    resolve_for_failed_or_cancelled(ports, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
    assert stored.park_path is None
    expected_reason = REASON_DEPENDENCY_ENDED.format(x=str(predecessor.id), status="failed")
    assert stored.park_reason == expected_reason


def test_resolve_for_failed_writes_gate_record_for_dependent() -> None:
    """A dependency park writes a 'dependency' event gate record."""
    predecessor = build_run(status="failed")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    ports = _make_ports([predecessor, dependent])

    resolve_for_failed_or_cancelled(ports, predecessor)

    records = ports.records.list_for_run(dependent.id)
    assert len(records) == 1
    assert records[0].event == "dependency"
    assert records[0].actor == "machine"


def test_resolve_for_cancelled_parks_dependent_as_dependency() -> None:
    """A cancelled predecessor parks its saved dependent with park_kind='dependency'."""
    predecessor = build_run(status="cancelled")
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})
    ports = _make_ports([predecessor, dependent])

    resolve_for_failed_or_cancelled(ports, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
    expected_reason = REASON_DEPENDENCY_ENDED.format(x=str(predecessor.id), status="cancelled")
    assert stored.park_reason == expected_reason


def test_resolve_for_failed_ignores_already_enqueued_dependents() -> None:
    """An already-enqueued dependent is not parked."""
    predecessor = build_run(status="failed")
    already_enqueued = build_run(
        status="queued", after_run_id=predecessor.id, engine_ref={"ref": 99}
    )
    ports = _make_ports([predecessor, already_enqueued])

    resolve_for_failed_or_cancelled(ports, predecessor)

    stored = ports.runs.get(already_enqueued.id)
    assert stored is not None
    # Not parked — still queued with engine_ref intact.
    assert stored.status == "queued"
    assert stored.park_kind is None


def test_resolve_for_failed_no_dependents_is_a_noop() -> None:
    """No queued dependents → nothing is written."""
    predecessor = build_run(status="failed")
    ports = _make_ports([predecessor])

    # Should not raise.
    resolve_for_failed_or_cancelled(ports, predecessor)

    records = ports.records.list_for_run(predecessor.id)
    assert records == []
