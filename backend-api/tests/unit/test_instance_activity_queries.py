"""`list_running` and `list_open` (AD-30): the two reads the instance activity joins.

The SQL adapters select on one column each and nothing else; the shared fakes return the
same sets in the same order. Also pairs `providers_instance` with a test module.
"""

from __future__ import annotations

import inspect
from datetime import timedelta

from orchestrator.api import providers_instance
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import AttemptRow, StepRunRow
from orchestrator.infrastructure.db.repositories import attempts as attempts_module
from orchestrator.infrastructure.db.repositories import step_runs as step_runs_module
from orchestrator.infrastructure.db.repositories.attempts import SQLAlchemyAttemptRepository
from orchestrator.infrastructure.db.repositories.step_runs import SQLAlchemyStepRunRepository
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.runs import FakeAttemptRepository, FakeStepRunRepository
from tests.unit.test_run_repository_adapter import RecordingSession


def a_step(run_id: object, seq: int, status: str) -> StepRun:
    return StepRun(  # type: ignore[call-arg]
        id=new_id(),
        run_id=run_id,  # type: ignore[arg-type]
        seq=seq,
        path=f"steps[{seq}]",
        label="x",
        kind="shell",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


def an_attempt(**over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "role": "agent",
        "status": "running",
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_the_running_rows_are_read_in_sql() -> None:
    step = a_step(new_id(), 1, "running")
    session = RecordingSession(scalars_queue=[[StepRunRow(**step_runs_module.row_values(step))]])

    found = SQLAlchemyStepRunRepository(session).list_running()  # type: ignore[arg-type]

    assert found == [step]
    rendered = str(session.statements[0])
    assert "step_run.status = :status_1" in rendered
    assert "ORDER BY step_run.run_id, step_run.seq" in rendered


def test_the_open_attempts_are_read_in_sql() -> None:
    attempt = an_attempt()
    session = RecordingSession(scalars_queue=[[AttemptRow(**attempts_module.row_values(attempt))]])

    found = SQLAlchemyAttemptRepository(session).list_open()  # type: ignore[arg-type]

    assert found == [attempt]
    rendered = str(session.statements[0])
    assert "attempt.ended_at IS NULL" in rendered
    assert "attempt.role =" not in rendered
    assert "ORDER BY attempt.started_at ASC NULLS LAST" in rendered


def test_the_fake_lists_only_running_rows_in_run_then_seq_order() -> None:
    run_a, run_b = sorted([new_id(), new_id()])
    late, early = a_step(run_b, 1, "running"), a_step(run_a, 2, "running")
    repository = FakeStepRunRepository([late, early, a_step(run_a, 1, "queued")])

    assert repository.list_running() == [early, late]


def test_the_fake_lists_open_attempts_of_every_role_started_first_unstarted_last() -> None:
    unstarted = an_attempt(role="session", status="queued")
    late = an_attempt(role="consult", started_at=EPOCH + timedelta(seconds=5))
    early = an_attempt(started_at=EPOCH)
    closed = an_attempt(started_at=EPOCH, ended_at=EPOCH, status="done")
    repository = FakeAttemptRepository([unstarted, late, closed, early])

    assert repository.list_open() == [early, late, unstarted]


def test_the_activity_provider_is_a_generator_function() -> None:
    assert inspect.isgeneratorfunction(providers_instance.activity_ports)
