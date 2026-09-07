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
different, smaller dependency set — `gateway`, `runs`, `steps`, `attempts`, `uow` — no
`records`/`clock`, since nothing here appends a gate record or reads the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
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
    uow: UnitOfWork


def record_attempt_spend(
    ports: SpendPorts, run: Run, attempt: Attempt, harness_usage: HarnessUsage | None
) -> None:
    """Price one attempt from the Gateway (falling back to `harness_usage`), then
    recompute `run.spend_usd` from every attempt the Run has."""
    with ports.uow:
        spend = ports.gateway.spend_for_attempt(run.id, attempt.id)
        priced = _priced_attempt(attempt, spend, harness_usage)
        if priced is not attempt:
            ports.attempts.update(priced)
        ports.runs.update(run.model_copy(update={"spend_usd": _run_spend(ports, run)}))
        ports.uow.commit()


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


def _run_spend(ports: SpendPorts, run: Run) -> Decimal:
    """Every attempt of every row of this Run, summed. Recomputed, never incremented — see
    the module docstring."""
    total = _ZERO
    for row in ports.steps.list_for_run(run.id):
        for row_attempt in ports.attempts.list_for_row(row.id):
            total += row_attempt.cost_usd or _ZERO
    return total
