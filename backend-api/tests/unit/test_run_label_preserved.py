"""No whole-row `update` of a Run reverts its label (story 3, AC7; ARCHITECTURE.md §6.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from orchestrator.application.use_cases.spend import SpendPorts, record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.infrastructure.db import SQLAlchemyRunRepository
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories import runs as runs_module
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.facts import FakeGatewayReadRepository
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository
from tests.unit.test_run_repository_adapter import RecordingSession, a_run

AT = datetime(2026, 11, 10, tzinfo=UTC)


def test_the_label_columns_are_not_whole_row_columns() -> None:
    assert "label" not in runs_module.MUTABLE_COLUMNS
    assert "label_set_by_operator" not in runs_module.MUTABLE_COLUMNS
    assert "status" in runs_module.MUTABLE_COLUMNS


def test_the_fake_keeps_the_label_set_by_set_label_over_a_stale_update() -> None:
    run = a_run()
    runs = FakeRunRepository([run])

    runs.set_label(run.id, "mine", True)
    runs.update(run.model_copy(update={"status": "running"}))

    stored = runs.runs[run.id]
    assert (stored.label, stored.label_set_by_operator, stored.status) == ("mine", True, "running")
    assert ("set_label", run.id) in runs.calls


def test_the_fake_set_label_refuses_an_unknown_id() -> None:
    with pytest.raises(ValueError):
        FakeRunRepository().set_label(new_id(), "x", False)


def test_the_adapter_update_leaves_the_stored_label() -> None:
    run = a_run()
    row = RunRow(**runs_module.row_values(run.model_copy(update={"label": "stored"})))
    row.label_set_by_operator = True
    session = RecordingSession(rows={run.id: row})

    SQLAlchemyRunRepository(session).update(  # type: ignore[arg-type]
        run.model_copy(update={"label": "stale", "label_set_by_operator": False, "status": "done"})
    )

    assert (row.label, row.label_set_by_operator, row.status) == ("stored", True, "done")


def test_the_adapter_set_label_locks_the_row_and_writes_both_columns() -> None:
    run = a_run()
    row = RunRow(**runs_module.row_values(run))
    session = RecordingSession(scalars_queue=[[row]])

    SQLAlchemyRunRepository(session).set_label(run.id, "mine", True)  # type: ignore[arg-type]

    statement = session.statements[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
    assert statement.get_execution_options()["populate_existing"] is True
    assert (row.label, row.label_set_by_operator) == ("mine", True)


def test_the_adapter_set_label_refuses_an_unknown_id() -> None:
    session = RecordingSession(scalars_queue=[[]])

    with pytest.raises(ValueError):
        SQLAlchemyRunRepository(session).set_label(new_id(), "x", False)  # type: ignore[arg-type]


def test_row_values_and_to_entity_round_trip_the_label() -> None:
    run = a_run(label="snake", label_set_by_operator=True)

    values = runs_module.row_values(run)
    row = RunRow(**values)

    assert (values["label"], values["label_set_by_operator"]) == ("snake", True)
    back: Run = runs_module.to_entity(row)
    assert (back.label, back.label_set_by_operator) == ("snake", True)


def test_an_unflushed_row_reads_as_the_empty_default() -> None:
    values: dict[str, Any] = runs_module.row_values(a_run())
    del values["label"], values["label_set_by_operator"]

    back = runs_module.to_entity(RunRow(**values))

    assert (back.label, back.label_set_by_operator) == ("", False)


def test_record_attempt_spend_on_a_stale_copy_keeps_the_label() -> None:
    run = Run(
        id=new_id(),
        project_id=UUID(int=1),
        repository_id=UUID(int=2),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("100"),
        created_at=AT,
    )
    row = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=0,
        path="a",
        label="a",
        kind="agent",
        gate="liveness",
        status="running",
    )
    attempt = Attempt(id=new_id(), run_id=run.id, step_run_id=row.id, n=1, status="running")
    runs = FakeRunRepository([run])
    gateway = FakeGateway()
    gateway.script(
        run.id,
        attempt.id,
        AttemptSpend(
            usd=Decimal("1"), tokens_in=1, tokens_out=1, by_model=(), calls=1, provisional=False
        ),
    )
    ports = SpendPorts(
        gateway=gateway,
        runs=runs,
        steps=FakeStepRunRepository([row]),
        attempts=FakeAttemptRepository([attempt]),
        gateway_reads=FakeGatewayReadRepository(),
        clock=FakeClock(),
        uow=FakeUnitOfWork(),
    )

    runs.set_label(run.id, "mine", True)
    record_attempt_spend(ports, run, attempt, None, locked=False)

    stored = runs.runs[run.id]
    assert (stored.label, stored.label_set_by_operator) == ("mine", True)
    assert stored.spend_usd == Decimal("1")
