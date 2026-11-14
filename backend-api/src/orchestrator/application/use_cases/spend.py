"""`record_attempt_spend` (AD-11): fill one attempt's cost, and recompute `run.spend_usd`.

`ports` leads the argument list, the same precedent every use case in this codebase sets
(`start_attempt(ports, run_id, seq, ...)`, `run_detail(ports, run_id)`) — see this story's
Design Notes for why the brief's `record_attempt_spend(run, attempt, harness_usage)` line
names the facts, not a literal signature.

**Settled beats provisional, always.** A Gateway answer that is not provisional (real rows
found) replaces whatever the attempt carried, and clears `cost_provisional`. Only when the
Gateway has nothing yet does `harness_usage` matter at all — the harness's own estimate,
carried with `cost_provisional=True`, or left untouched when there is no harness estimate
either (this story's own Design Notes: "there is nothing new to write, and inventing zeros
would misrepresent 'unknown' as 'free'").

**`run.spend_usd` is not incremented — it is recomputed**, by summing every attempt's own
`cost_usd` across every row of the Run. That is what makes a later, settling call safe to
replay: the second call's figures *replace* the first's on the one attempt they are both
about, so summing again never double-counts.

**Not `WriterPorts`.** `SpendPorts` is its own bundle (Design Notes): a different write, a
different, smaller dependency set — `gateway`, `runs`, `steps`, `attempts`,
`gateway_reads`, `clock`, `uow`, and an optional `fact_sets` the budget gate reads migrated
harness money through — no `records`, since nothing here appends a gate record.
The clock stamps the `gateway_read` each call stores (SPEC CAP-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.spend_figures import (
    AttemptRows,
    figures_of,
    first_fact_money,
    gateway_read_for,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import GatewayTrigger, UsageFact
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository, GatewayReadRepository
from orchestrator.domain.ports.gateway import AttemptSpend, Gateway, ModelSpend
from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: A stored `cost_usd` of `None` — an attempt nothing has priced yet — sums as zero.
_ZERO = Decimal("0")


@dataclass(frozen=True)
class SpendPorts:
    """What `record_attempt_spend` reads and writes through. See the module docstring for
    why this is not `WriterPorts`."""

    gateway: Gateway
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    gateway_reads: GatewayReadRepository
    clock: Clock
    uow: UnitOfWork
    fact_sets: FactSetRepository | None = None


def record_attempt_spend(
    ports: SpendPorts,
    run: Run,
    attempt: Attempt,
    harness_usage: HarnessUsage | None,
    *,
    locked: bool = False,
) -> Run:
    """Price one attempt from the Gateway (falling back to `harness_usage`), then
    recompute `run.spend_usd` from every attempt the Run has, and return the updated Run
    — the same `set_run` shape every other writer in this codebase returns, and what the
    budget check (5.7's own caller) reads without a second repository round trip.

    `locked` re-reads the Run under its row lock inside this unit of work, for a writer
    outside the walk whose copy may predate a `cancel` (AD-8 as amended for AD-23)."""
    with ports.uow:
        if locked:
            run = ports.runs.get_for_update(run.id) or run
        spend = ports.gateway.spend_for_attempt(run.id, attempt.id)
        ports.gateway_reads.add(
            *gateway_read_for(attempt, spend, harness_usage, new_id(), ports.clock.now())
        )
        priced = _priced_attempt(attempt, spend, harness_usage)
        if priced is not attempt:
            ports.attempts.update(priced)
        total, provisional, attempts = _run_spend_and_provisional(ports, run)
        updated = run.model_copy(
            update={
                "spend_usd": total,
                "spend_provisional": provisional,
                **_figure_columns(attempts),
            }
        )
        ports.runs.update(updated)
        ports.uow.commit()
        return updated


def reread_gateway_for_run(ports: SpendPorts, run_id: UUID, trigger: GatewayTrigger) -> Run:
    """Read the gateway again for every harness attempt of the Run and recompute its five gate
    columns. `spend_usd` and each attempt's `cost_usd` stay as they are (ARCHITECTURE §5.4)."""
    with ports.uow:
        run = ports.runs.get_for_update(run_id)
        if run is None:
            raise NotFound(f"no run {run_id}")
        for row in ports.steps.list_for_run(run_id):
            for attempt in ports.attempts.list_for_row(row.id):
                if not attempt.harness:
                    continue
                spend = ports.gateway.spend_for_attempt(run_id, attempt.id)
                read, usage = gateway_read_for(attempt, spend, None, new_id(), ports.clock.now())
                ports.gateway_reads.add(read.model_copy(update={"trigger": trigger}), usage)
        _total, _provisional, attempts = _run_spend_and_provisional(ports, run)
        updated = run.model_copy(update=_figure_columns(attempts))
        ports.runs.update(updated)
        ports.uow.commit()
        return updated


def _figure_columns(attempts: list[AttemptRows]) -> dict[str, Decimal | bool]:
    spent = figures_of(attempts)
    return {
        "gateway_spend_usd": spent.gateway_usd,
        "harness_spend_usd": spent.harness_usd,
        "gate_spend_usd": spent.gate_usd,
        "gateway_reported": spent.gateway_reported,
        "harness_reported": spent.harness_reported,
    }


def _priced_attempt(
    attempt: Attempt, spend: AttemptSpend, harness_usage: HarnessUsage | None
) -> Attempt:
    if not spend.provisional:
        model = attempt.model or _dominant_model(spend.by_model)
        return attempt.model_copy(
            update={
                "cost_usd": spend.usd,
                "tokens_in": spend.tokens_in,
                "tokens_out": spend.tokens_out,
                "cost_provisional": False,
                "model": model,
            }
        )
    if harness_usage is not None:
        return attempt.model_copy(
            update={
                "cost_usd": harness_usage.cost_usd,
                "tokens_in": harness_usage.tokens_in,
                "tokens_out": harness_usage.tokens_out,
                "cost_provisional": True,
            }
        )
    if attempt.cost_provisional:
        return attempt
    return attempt.model_copy(update={"cost_provisional": True})


def _dominant_model(by_model: tuple[ModelSpend, ...]) -> str | None:
    """The model with the largest `usd` share, or `None` for an attempt with no rows at
    all (spend fully settled at zero) — the model a stored attempt should be attributed
    to when nothing ever set `attempt.model` (a `local`/pre-5.4 dispatch, say).

    A tie on `usd` is broken by `model` itself, alphabetically last — a stated rule rather
    than whatever order the adapter's dict happened to iterate in.
    """
    if not by_model:
        return None
    return max(by_model, key=lambda model_spend: (model_spend.usd, model_spend.model)).model


def _run_spend_and_provisional(
    ports: SpendPorts, run: Run
) -> tuple[Decimal, bool, list[AttemptRows]]:
    """Every attempt of every row of this Run, summed, plus a flag that is `True` when any
    attempt carries `cost_provisional=True`. Recomputed in one pass, never incremented — see
    the module docstring."""
    total = _ZERO
    provisional = False
    attempts: list[AttemptRows] = []
    for row in ports.steps.list_for_run(run.id):
        for row_attempt in ports.attempts.list_for_row(row.id):
            total += row_attempt.cost_usd or _ZERO
            if row_attempt.cost_provisional:
                provisional = True
            attempts.append(
                AttemptRows(
                    reads=[
                        (r, ports.gateway_reads.usage(r.id))
                        for r in ports.gateway_reads.list_for_attempt(row_attempt.id)
                    ],
                    fact_money=_fact_set_money(ports, row_attempt.id),
                )
            )
    return total, provisional, attempts


def _fact_set_money(ports: SpendPorts, attempt_id: UUID) -> tuple[UsageFact, ...]:
    if ports.fact_sets is None:
        return ()
    return first_fact_money(ports.fact_sets, attempt_id)
