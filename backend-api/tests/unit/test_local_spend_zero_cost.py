"""A local model costs nothing and still reports tokens (PRD §11, FR-28, story 7.3).

The brief's own wording: "The Gateway's spend rows for local models carry `spend 0`;
`record_attempt_spend` keeps tokens and cost `0`, **not provisional when rows exist**."

That last clause is the whole point, and it is the one thing a zero could otherwise destroy.
`cost_provisional` is what says "this number is the harness's estimate, not the Gateway's
settled spend", and `AttemptSpend.provisional` is answered by whether the spend log had rows —
not by whether the money was more than nothing. So a `local` attempt whose model is served on
the host must come out of pricing as **measured zero**, indistinguishable in `cost_usd` from a
Run that never made a call and distinguishable from it in every other field: tokens counted,
calls counted, `cost_provisional` false.

Nothing in `application/use_cases/spend.py` changes for this. That is the finding, and it is
covered here rather than assumed, because "free" and "unknown" collapsing into one another is
the exact failure SM-3's cost comparison across the three harnesses would be built on.
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
from orchestrator.domain.ports.harness import HarnessUsage
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 10, tzinfo=UTC)
LOCAL_MODEL = "local-coder"
TOKENS_IN = 880
TOKENS_OUT = 210


class Ports:
    """The five repositories `record_attempt_spend` writes through, as fakes (AD-18)."""

    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gateway = FakeGateway()
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
        harness="local",
        model=LOCAL_MODEL,
    )


def zero_spend_rows() -> AttemptSpend:
    """What LiteLLM's spend log holds for a model served on the host: real rows, no money."""
    return AttemptSpend(
        usd=Decimal("0"),
        tokens_in=TOKENS_IN,
        tokens_out=TOKENS_OUT,
        by_model=(
            ModelSpend(
                model=LOCAL_MODEL, usd=Decimal("0"), tokens_in=TOKENS_IN, tokens_out=TOKENS_OUT
            ),
        ),
        calls=3,
        provisional=False,
    )


def priced(harness_usage: HarnessUsage | None = None) -> Attempt:
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)
    ports.gateway.script(run.id, attempt.id, zero_spend_rows())

    record_attempt_spend(ports.bundle(), run, attempt, harness_usage)

    return ports.attempts.attempts[attempt.id]


def test_a_local_attempt_is_priced_at_zero_with_its_tokens() -> None:
    stored = priced()

    assert stored.cost_usd == Decimal("0")
    assert stored.tokens_in == TOKENS_IN
    assert stored.tokens_out == TOKENS_OUT


def test_a_measured_zero_is_not_provisional() -> None:
    """Rows existed, so the figure is the Gateway's settled one. `cost_provisional` false is
    what lets the trajectory export state a local Story's cost as a fact."""
    assert priced().cost_provisional is False


def test_the_harnesss_own_zero_does_not_displace_the_gateways() -> None:
    """Settled beats provisional, always — even when both say zero, because only one of them
    also carries the Gateway's own token counts and call count."""
    stored = priced(HarnessUsage(tokens_in=1, tokens_out=1, cost_usd=Decimal("0")))

    assert stored.cost_provisional is False
    assert stored.tokens_in == TOKENS_IN


def test_the_local_model_stays_the_attempts_model() -> None:
    assert priced().model == LOCAL_MODEL


def test_the_runs_spend_is_recomputed_and_stays_zero() -> None:
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)
    ports.gateway.script(run.id, attempt.id, zero_spend_rows())

    updated = record_attempt_spend(ports.bundle(), run, attempt, None)

    assert updated.spend_usd == Decimal("0")


def test_an_attempt_the_gateway_has_no_rows_for_is_still_provisional() -> None:
    """The contrast that makes the assertions above mean something: "free" and "unknown" are
    two different states, and only one of them is a measurement."""
    ports = Ports()
    run = a_run()
    ports.runs.add(run)
    row = a_row(run)
    ports.steps.add_many([row])
    attempt = an_attempt(run, row)
    ports.attempts.add(attempt)

    record_attempt_spend(ports.bundle(), run, attempt, None)

    assert ports.attempts.attempts[attempt.id].cost_provisional is True
