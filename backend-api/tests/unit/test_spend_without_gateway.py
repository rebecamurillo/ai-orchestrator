"""record_attempt_spend with DisabledGateway (story 9-3 ACs 4-6).

`DisabledGateway` always returns PROVISIONAL_ZERO (`provisional=True`), so
`record_attempt_spend` uses `harness_usage` when provided (AC 4), leaves `cost_usd`
as `None` when there is no harness estimate (AC 5), and `budget.py::check` parks
correctly on those harness figures (AC 6).

Replicates `test_local_spend_zero_cost.py`'s `Ports`/`a_run`/`a_row`/`an_attempt`
helper pattern with `DisabledGateway()` as `ports.gateway`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.rules import budget
from orchestrator.application.use_cases.spend import SpendPorts, record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.infrastructure.gateway.disabled import DisabledGateway
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 13, tzinfo=UTC)
TOKENS_IN = 1200
TOKENS_OUT = 300


class Ports:
    """The five repositories `record_attempt_spend` writes through, as fakes (AD-18)."""

    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gateway = DisabledGateway()
        self.uow = FakeUnitOfWork()

    def bundle(self) -> SpendPorts:
        return SpendPorts(
            gateway=self.gateway,
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            uow=self.uow,
        )


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("40"),
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


def an_attempt(run: Run, row: StepRun) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=1,
        status="running",
        harness="claude",
        model="claude-sonnet-4-5",
    )


# --- AC 4: harness usage is stored when gateway is disabled ---


def test_record_attempt_spend_stores_harness_cost_usd() -> None:
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    harness_usage = HarnessUsage(
        tokens_in=TOKENS_IN, tokens_out=TOKENS_OUT, cost_usd=Decimal("0.42")
    )
    record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    stored = ports.attempts.attempts[attempt.id]
    assert stored.cost_usd == Decimal("0.42")
    assert stored.tokens_in == TOKENS_IN
    assert stored.tokens_out == TOKENS_OUT


def test_record_attempt_spend_with_harness_usage_is_provisional() -> None:
    """DisabledGateway returns provisional=True, so the harness estimate is kept provisional."""
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    harness_usage = HarnessUsage(
        tokens_in=TOKENS_IN, tokens_out=TOKENS_OUT, cost_usd=Decimal("0.42")
    )
    record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    assert ports.attempts.attempts[attempt.id].cost_provisional is True


def test_run_spend_equals_sum_of_attempts_cost_usd() -> None:
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    harness_usage = HarnessUsage(
        tokens_in=TOKENS_IN, tokens_out=TOKENS_OUT, cost_usd=Decimal("0.42")
    )
    updated_run = record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    assert updated_run.spend_usd == Decimal("0.42")


# --- AC 5: no harness usage — cost_usd stays None, not written as $0.00 ---


def test_record_attempt_spend_without_harness_leaves_cost_usd_none() -> None:
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    record_attempt_spend(ports.bundle(), run, attempt, None)

    stored = ports.attempts.attempts[attempt.id]
    assert stored.cost_usd is None


# --- AC 6: budget.py::check parks when run.spend_usd > run.budget_usd ---


def test_budget_check_parks_when_spend_exceeds_budget() -> None:
    """Budget parking works off harness figures even when the gateway is disabled."""
    ports = Ports()
    run = a_run()  # budget_usd=Decimal("40")
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    # A harness spend that exceeds the budget
    harness_usage = HarnessUsage(tokens_in=10000, tokens_out=5000, cost_usd=Decimal("50.00"))
    updated_run = record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    result = budget.check(updated_run)
    assert result is not None
    assert result.kind == "budget"


def test_budget_check_does_not_park_when_within_budget() -> None:
    ports = Ports()
    run = a_run()  # budget_usd=Decimal("40")
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    harness_usage = HarnessUsage(tokens_in=100, tokens_out=50, cost_usd=Decimal("1.00"))
    updated_run = record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    assert budget.check(updated_run) is None
