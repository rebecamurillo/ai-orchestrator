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


def figures(reads_by_attempt: Iterable[Sequence[StoredRead]]) -> SpendFigures:
    """`reads_by_attempt`: one newest-first sequence of stored reads per attempt."""
    gateway = _ZERO
    harness = _ZERO
    gateway_reported = False
    harness_reported = False
    for reads in reads_by_attempt:
        if reads and not reads[0][0].provisional:
            gateway += reads[0][0].usd
            gateway_reported = True
        money = next(
            (rows for _, usage in reads if (rows := _harness_money(usage))),
            (),
        )
        if money:
            harness += sum((u.usd or _ZERO for u in money), _ZERO)
            harness_reported = True
    reported = [
        total for total, flag in ((gateway, gateway_reported), (harness, harness_reported)) if flag
    ]
    return SpendFigures(
        gateway_usd=gateway,
        harness_usd=harness,
        gate_usd=max(reported, default=_ZERO),
        gateway_reported=gateway_reported,
        harness_reported=harness_reported,
    )


def _harness_money(usage: Sequence[UsageFact]) -> tuple[UsageFact, ...]:
    return tuple(u for u in usage if u.source == "harness" and u.usage_class == "money")
