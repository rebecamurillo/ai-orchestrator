"""`signal_run` with `kind="start"` when `SignalPorts.preflight` is `None` (story 5-3).

Covers the guard at `signal_run.py:191`:

    if ports.preflight is None:
        raise Conflict("start signal requires preflight; call site is missing it")

This branch is unreachable from production code because `signal_effect_ports` in
`providers.py` always wires `preflight` for start signals (bad_spec repair, 2026-09-18).
The test exists solely to satisfy the 100 % branch-coverage requirement on
`orchestrator.application` (`make test --fail-under=100`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")
START = Signal(kind="start", payload={})


def _a_saved_run() -> Run:
    """A saved run that would pass `validate` but fails when preflight is missing."""
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="repo-init",
        template_version=1,
        status="queued",
        budget_usd=BUDGET,
        created_at=NOW,
        engine_ref={},
        inputs={"base_branch": "main", "harness": "claude", "model": None},
    )


def test_start_signal_missing_preflight_raises_conflict() -> None:
    """Sending `kind="start"` when `ports.preflight is None` raises 409 Conflict.

    This guards against a call site that constructs `SignalPorts` without wiring
    `preflight`. The error is a `Conflict` (409) rather than an `AssertionError` (500)
    so the client receives a meaningful response even in the unlikely event that
    `providers.py` is refactored and the wiring is accidentally dropped.
    """
    run = _a_saved_run()
    run_repo = FakeRunRepository([run])
    writer_ports = WriterPorts(
        runs=run_repo,
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=FakeUnitOfWork(),
        clock=FakeClock(NOW),
    )
    ports = SignalPorts(
        writers=writer_ports,
        engine=FakeWorkflowEngine(),
        preflight=None,  # deliberately omitted — this is the path under test
    )

    with pytest.raises(Conflict):
        signal_run(ports, run.id, START)
