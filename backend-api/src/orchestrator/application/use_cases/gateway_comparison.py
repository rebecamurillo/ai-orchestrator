"""Per attempt, the gateway reads beside the harness figure (SPEC CAP-6). Reads, writes nothing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.metrics.live import MetricsReadPorts
from orchestrator.application.metrics.roles import role_of
from orchestrator.application.use_cases.spend_figures import first_fact_money, harness_money
from orchestrator.domain.entities.facts import GatewayRead
from orchestrator.domain.errors import NotFound


@dataclass(frozen=True)
class AttemptGatewayReads:
    attempt_id: UUID
    row_path: str
    attempt_n: int
    role: str
    harness_usd: Decimal | None
    reads: tuple[GatewayRead, ...]


def gateway_comparison(ports: MetricsReadPorts, run_id: UUID) -> list[AttemptGatewayReads]:
    if ports.runs.get(run_id) is None:
        raise NotFound(f"no run {run_id}")
    items: list[AttemptGatewayReads] = []
    for row in sorted(ports.steps.list_for_run(run_id), key=lambda r: r.seq):
        for attempt in ports.attempts.list_for_row(row.id):
            newest_first = ports.gateway_reads.list_for_attempt(attempt.id)
            newest_first.sort(key=lambda r: r.read_at, reverse=True)
            money = next(
                (
                    rows
                    for read in newest_first
                    if (rows := harness_money(ports.gateway_reads.usage(read.id)))
                ),
                first_fact_money(ports.fact_sets, attempt.id),
            )
            items.append(
                AttemptGatewayReads(
                    attempt_id=attempt.id,
                    row_path=row.path,
                    attempt_n=attempt.n,
                    role=role_of(attempt, row),
                    harness_usd=sum((u.usd or Decimal(0) for u in money), Decimal(0))
                    if money
                    else None,
                    reads=tuple(reversed(newest_first)),
                )
            )
    return items
