"""`record_attempt_spend` — settled figures, provisional + harness usage (and without it),
a later call replacing provisional figures, `run.spend_usd` recomputed both times, and the
dominant-model pick when `attempt.model` was unset. TDD first (AD-18).
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
from orchestrator.domain.ports.harness import HarnessUsage
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def a_run(**overrides: object) -> Run:
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
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run: Run, *, seq: int) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=f"stories[{seq}].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
    )


def an_attempt(row: StepRun, run: Run, **overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run.id,
        "step_run_id": row.id,
        "n": 1,
        "status": "running",
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


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


def _settled(usd: str, tokens_in: int, tokens_out: int, model: str = "gpt-5") -> AttemptSpend:
    model_spend = ModelSpend(
        model=model, usd=Decimal(usd), tokens_in=tokens_in, tokens_out=tokens_out
    )
    return AttemptSpend(
        usd=Decimal(usd),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        by_model=(model_spend,),
        calls=1,
        provisional=False,
    )


def test_settled_gateway_figures_are_stored_and_run_spend_is_recomputed() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    harness.gateway.script(run.id, attempt.id, _settled("3.50", 100, 50))

    record_attempt_spend(harness.ports(), run, attempt, None)

    stored = harness.attempts.attempts[attempt.id]
    assert stored.cost_usd == Decimal("3.50")
    assert stored.tokens_in == 100  # noqa: PLR2004
    assert stored.tokens_out == 50  # noqa: PLR2004
    assert stored.cost_provisional is False
    assert harness.runs.runs[run.id].spend_usd == Decimal("3.50")


def test_settled_figures_pick_the_dominant_model_when_unset() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    spend = AttemptSpend(
        usd=Decimal("3.0"),
        tokens_in=30,
        tokens_out=15,
        by_model=(
            ModelSpend(model="small", usd=Decimal("1.0"), tokens_in=10, tokens_out=5),
            ModelSpend(model="big", usd=Decimal("2.0"), tokens_in=20, tokens_out=10),
        ),
        calls=2,
        provisional=False,
    )
    harness.gateway.script(run.id, attempt.id, spend)

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert harness.attempts.attempts[attempt.id].model == "big"


def test_settled_figures_break_a_dominant_model_tie_alphabetically_last() -> None:
    """Two models tied at the same `usd` — `_dominant_model`'s tie-break is `model` itself,
    alphabetically last, not whatever order the adapter's dict happened to iterate in."""
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    spend = AttemptSpend(
        usd=Decimal("2.0"),
        tokens_in=20,
        tokens_out=10,
        by_model=(
            ModelSpend(model="beta", usd=Decimal("1.0"), tokens_in=10, tokens_out=5),
            ModelSpend(model="alpha", usd=Decimal("1.0"), tokens_in=10, tokens_out=5),
        ),
        calls=2,
        provisional=False,
    )
    harness.gateway.script(run.id, attempt.id, spend)

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert harness.attempts.attempts[attempt.id].model == "beta"


def test_settled_figures_leave_an_already_set_model_alone() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run, model="claude-opus-5")
    harness.attempts.add(attempt)
    harness.gateway.script(run.id, attempt.id, _settled("1.0", 10, 5, model="gpt-5"))

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert harness.attempts.attempts[attempt.id].model == "claude-opus-5"


def test_provisional_with_harness_usage_stores_the_harness_figures() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    usage = HarnessUsage(tokens_in=42, tokens_out=7, cost_usd=Decimal("0.75"))

    record_attempt_spend(harness.ports(), run, attempt, usage)

    stored = harness.attempts.attempts[attempt.id]
    assert stored.cost_usd == Decimal("0.75")
    assert stored.tokens_in == 42  # noqa: PLR2004
    assert stored.tokens_out == 7  # noqa: PLR2004
    assert stored.cost_provisional is True
    assert harness.runs.runs[run.id].spend_usd == Decimal("0.75")


def test_provisional_with_no_harness_usage_leaves_cost_fields_untouched() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run, cost_usd=Decimal("9.99"), cost_provisional=False)
    harness.attempts.add(attempt)

    record_attempt_spend(harness.ports(), run, attempt, None)

    stored = harness.attempts.attempts[attempt.id]
    assert stored.cost_usd == Decimal("9.99")
    assert stored.cost_provisional is True
    assert harness.runs.runs[run.id].spend_usd == Decimal("9.99")


def test_a_later_settled_call_replaces_the_provisional_figures_and_clears_the_flag() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    usage = HarnessUsage(tokens_in=42, tokens_out=7, cost_usd=Decimal("0.75"))

    record_attempt_spend(harness.ports(), run, attempt, usage)
    provisional = harness.attempts.attempts[attempt.id]
    assert harness.runs.runs[run.id].spend_usd == Decimal("0.75")

    harness.gateway.script(run.id, attempt.id, _settled("3.50", 100, 50))
    record_attempt_spend(harness.ports(), run, provisional, None)

    settled = harness.attempts.attempts[attempt.id]
    assert settled.cost_usd == Decimal("3.50")
    assert settled.cost_provisional is False
    assert harness.runs.runs[run.id].spend_usd == Decimal("3.50")


def test_provisional_already_set_and_no_harness_usage_writes_nothing_to_the_attempt() -> None:
    """The attempt is returned unchanged (same instance) — `record_attempt_spend` skips the
    write entirely rather than re-storing an identical value."""
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run, cost_provisional=True)
    harness.attempts.add(attempt)
    harness.attempts.calls.clear()

    record_attempt_spend(harness.ports(), run, attempt, None)

    assert all(call[0] != "update" for call in harness.attempts.calls)
    assert harness.attempts.attempts[attempt.id] == attempt


def test_settled_with_no_rows_and_no_prior_model_leaves_model_unset() -> None:
    """A settled answer with an empty `by_model` (no spend-log rows at all) has no model to
    attribute — `_dominant_model` answers `None` rather than raising on an empty sequence."""
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row = a_row(run, seq=0)
    harness.steps.add_many([row])
    attempt = an_attempt(row, run)
    harness.attempts.add(attempt)
    spend = AttemptSpend(
        usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=False
    )
    harness.gateway.script(run.id, attempt.id, spend)

    record_attempt_spend(harness.ports(), run, attempt, None)

    stored = harness.attempts.attempts[attempt.id]
    assert stored.model is None
    assert stored.cost_provisional is False


def test_run_spend_sums_every_attempt_of_every_row() -> None:
    harness = Harness()
    run = a_run()
    harness.runs.add(run)
    row_a = a_row(run, seq=0)
    row_b = a_row(run, seq=1)
    harness.steps.add_many([row_a, row_b])
    attempt_a = an_attempt(row_a, run, cost_usd=Decimal("1.00"), cost_provisional=False)
    attempt_b = an_attempt(row_b, run, cost_usd=Decimal("2.00"), cost_provisional=False)
    harness.attempts.add(attempt_a)
    harness.attempts.add(attempt_b)
    target = an_attempt(row_a, run, n=2)
    harness.attempts.add(target)
    harness.gateway.script(run.id, target.id, _settled("0.50", 5, 5))

    record_attempt_spend(harness.ports(), run, target, None)

    assert harness.runs.runs[run.id].spend_usd == Decimal("3.50")
