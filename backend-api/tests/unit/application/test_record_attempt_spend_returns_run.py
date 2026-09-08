"""`record_attempt_spend` returns the updated Run (5.7): the `set_run` shape every other
writer in this codebase returns, and what the budget check reads without a second
repository round trip. `test_record_attempt_spend.py` (frozen, 5.3) never captured a
return value, so this is new coverage rather than a changed assertion. TDD first (AD-18).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.spend import SpendPorts, record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def a_run(**over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("100"),
        "created_at": NOW,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run: Run) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=0,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
    )


def an_attempt(row: StepRun, run: Run) -> Attempt:
    return Attempt(id=new_id(), run_id=run.id, step_run_id=row.id, n=1, status="running")


def test_the_returned_run_carries_the_recomputed_spend() -> None:
    run = a_run()
    row = a_row(run)
    attempt = an_attempt(row, run)
    runs, steps, attempts = (
        FakeRunRepository([run]),
        FakeStepRunRepository([row]),
        (FakeAttemptRepository([attempt])),
    )
    gateway = FakeGateway()
    gateway.script(
        run.id,
        attempt.id,
        AttemptSpend(
            usd=Decimal("3.50"),
            tokens_in=10,
            tokens_out=5,
            by_model=(ModelSpend(model="gpt-5", usd=Decimal("3.50"), tokens_in=10, tokens_out=5),),
            calls=1,
            provisional=False,
        ),
    )
    ports = SpendPorts(
        gateway=gateway, runs=runs, steps=steps, attempts=attempts, uow=FakeUnitOfWork()
    )

    updated = record_attempt_spend(ports, run, attempt, None)

    assert updated.spend_usd == Decimal("3.50")
    assert updated is runs.runs[run.id]
