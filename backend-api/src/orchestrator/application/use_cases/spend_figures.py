"""The gateway read and the spend figures of a Run (SPEC CAP-5; RM-4).

`gateway_read_for` turns what one attempt-end spend record learned into the rows stored for
it. `figures` recomputes the Run's gateway, harness and gate totals from the stored reads —
sums over every attempt, never increments, so recording an attempt again changes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import GatewayRead, UsageFact
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.domain.ports.harness import HarnessUsage

_ZERO = Decimal("0")

StoredRead = tuple[GatewayRead, tuple[UsageFact, ...]]


@dataclass(frozen=True)
class SpendFigures:
    gateway_usd: Decimal
    harness_usd: Decimal
    gate_usd: Decimal
    gateway_reported: bool
    harness_reported: bool


def gateway_read_for(
    attempt: Attempt,
    spend: AttemptSpend,
    harness_usage: HarnessUsage | None,
    read_id: UUID,
    at: datetime,
) -> StoredRead:
    read = GatewayRead(
        id=read_id,
        attempt_id=attempt.id,
        run_id=attempt.run_id,
        read_at=at,
        trigger="attempt_end",
        rows=spend.calls,
        calls=spend.calls,
        provisional=spend.provisional,
        capped=spend.capped,
        usd=spend.usd,
        prompt=spend.tokens_in,
        completion=spend.tokens_out,
    )
    usage: list[UsageFact] = []
    for model in spend.by_model:
        usage.append(
            UsageFact(source="gateway", model=model.model, usage_class="money", usd=model.usd)
        )
        usage.append(
            UsageFact(
                source="gateway",
                model=model.model,
                usage_class="gateway_prompt",
                tokens=model.tokens_in,
            )
        )
        usage.append(
            UsageFact(
                source="gateway",
                model=model.model,
                usage_class="gateway_completion",
                tokens=model.tokens_out,
            )
        )
    if harness_usage is not None:
        usage.append(
            UsageFact(
                source="harness",
                model=attempt.model,
                usage_class="money",
                usd=harness_usage.cost_usd,
            )
        )
    return read, tuple(usage)


@dataclass(frozen=True)
class AttemptRows:
    """What one attempt's figures are computed from: its stored reads (newest first) and the
    harness `money` rows of one of its fact sets."""

    reads: Sequence[StoredRead] = ()
    fact_money: tuple[UsageFact, ...] = ()


def figures(reads_by_attempt: Iterable[Sequence[StoredRead]]) -> SpendFigures:
    """`figures_of` over attempts that carry reads only."""
    return figures_of(AttemptRows(reads=reads) for reads in reads_by_attempt)


def figures_of(attempts: Iterable[AttemptRows]) -> SpendFigures:
    """Per attempt, the gateway figure is its newest settled read, else its newest provisional
    one: settled beats provisional, so a replay's provisional read never hides a settled
    figure. The harness figure is the harness money rows of its newest read that has any,
    else its fact-set rows — counted once. The gate sums, per attempt, the higher of that
    attempt's reported figures (operator answers 2026-11-13, stories 5 and 6): a max of the
    two Run totals reads below the real spend when attempts report through different sources.
    """
    gateway = _ZERO
    harness = _ZERO
    gate = _ZERO
    gateway_reported = False
    harness_reported = False
    for attempt in attempts:
        reads = attempt.reads
        reported: list[Decimal] = []
        settled = next((read for read, _ in reads if not read.provisional), None)
        newest = settled or (reads[0][0] if reads else None)
        if newest is not None:
            gateway += newest.usd
        if settled is not None:
            reported.append(settled.usd)
            gateway_reported = True
        money = next(
            (rows for _, usage in reads if (rows := _harness_money(usage))),
            _harness_money(attempt.fact_money),
        )
        if money:
            attempt_harness = sum((u.usd or _ZERO for u in money), _ZERO)
            harness += attempt_harness
            reported.append(attempt_harness)
            harness_reported = True
        gate += max(reported, default=_ZERO)
    return SpendFigures(
        gateway_usd=gateway,
        harness_usd=harness,
        gate_usd=gate,
        gateway_reported=gateway_reported,
        harness_reported=harness_reported,
    )


def _harness_money(usage: Sequence[UsageFact]) -> tuple[UsageFact, ...]:
    return tuple(u for u in usage if u.source == "harness" and u.usage_class == "money")
