"""`record_attempt_spend` — `run.spend_provisional` propagation (story 8-6).

`test_record_attempt_spend.py` is frozen (root AGENTS.md hard rule 1); this file adds
coverage for the new `spend_provisional` field without touching the original assertions.

`_run_spend_and_provisional` (inside `spend.py`) accumulates the provisional flag from
`attempt.cost_provisional` in the same pass as `spend_usd`. These tests verify that the
stored `run.spend_provisional` reflects that accumulation — a silent regression here would
cause `project_spend.project_metrics()` to always return `monthly_spend_provisional=False`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.spend import SpendPorts, record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="dev",
        template_version=1,
        status="running",
        budget_usd=Decimal("100"),
        created_at=NOW,
    )


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
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=1,
        status="running",
    )


def _provisional_spend(usd: str) -> AttemptSpend:
    model_spend = ModelSpend(
        model="gpt-5",
        usd=Decimal(usd),
        tokens_in=10,
        tokens_out=10,
    )
    return AttemptSpend(
        usd=Decimal(usd),
        tokens_in=10,
        tokens_out=10,
        by_model=(model_spend,),
        calls=1,
        provisional=True,
    )


def _settled_spend(usd: str) -> AttemptSpend:
    model_spend = ModelSpend(
        model="gpt-5",
        usd=Decimal(usd),
        tokens_in=10,
        tokens_out=10,
    )
    return AttemptSpend(
        usd=Decimal(usd),
        tokens_in=10,
        tokens_out=10,
        by_model=(model_spend,),
        calls=1,
        provisional=False,
    )


class Harness:
    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gateway = FakeGateway()
        self.uow = FakeUnitOfWork()

    def ports(self) -> SpendPorts:
        return SpendPorts(
            gateway=self.gateway,
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            uow=self.uow,
        )


def test_spend_provisional_set_true_when_gateway_answer_is_provisional() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    harness.gateway.script(run.id, attempt.id, _provisional_spend("0.75"))

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert harness.runs.runs[run.id].spend_provisional is True


def test_spend_provisional_remains_false_when_all_attempts_are_settled() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    harness.gateway.script(run.id, attempt.id, _settled_spend("3.50"))

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert harness.runs.runs[run.id].spend_provisional is False


def test_spend_provisional_cleared_when_later_settled_call_replaces_provisional() -> None:
    """A provisional run that later settles: spend_provisional must flip to False.

    This verifies `_run_spend_and_provisional` recomputes the flag on every call — a
    run whose only attempt has settled must never keep `spend_provisional=True`.
    """
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    harness.gateway.script(run.id, attempt.id, _provisional_spend("0.75"))

    provisional_run = record_attempt_spend(harness.ports(), run, attempt, None)
    assert harness.runs.runs[run.id].spend_provisional is True

    harness.gateway.script(run.id, attempt.id, _settled_spend("3.50"))
    settled_attempt = harness.attempts.attempts[attempt.id]
    record_attempt_spend(harness.ports(), provisional_run, settled_attempt, None)

    assert harness.runs.runs[run.id].spend_provisional is False
