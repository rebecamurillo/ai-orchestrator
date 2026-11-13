"""`figures_of` counts a fact set's harness money for an attempt no read reports harness
money for (story 6, operator answer 2026-11-13); a read's harness row wins."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.spend_figures import (
    AttemptRows,
    StoredRead,
    figures,
    figures_of,
)
from orchestrator.domain.entities.facts import GatewayRead, UsageFact
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def harness_money(usd: str) -> UsageFact:
    return UsageFact(source="harness", usage_class="money", usd=Decimal(usd))


def read(usd: str, *usage: UsageFact, provisional: bool = False) -> StoredRead:
    return (
        GatewayRead(
            id=new_id(),
            attempt_id=new_id(),
            run_id=new_id(),
            read_at=NOW,
            trigger="attempt_end",
            provisional=provisional,
            usd=Decimal(usd),
        ),
        usage,
    )


def test_fact_set_harness_money_counts_when_no_read_has_any() -> None:
    got = figures_of([AttemptRows(fact_money=(harness_money("0.30"),))])

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (
        Decimal("0"),
        Decimal("0.30"),
        Decimal("0.30"),
    )
    assert (got.gateway_reported, got.harness_reported) == (False, True)


def test_a_reads_harness_row_wins_over_fact_set_rows() -> None:
    attempt = AttemptRows(
        reads=[read("1", harness_money("0.50"))],
        fact_money=(harness_money("0.20"), harness_money("0.28")),
    )

    got = figures_of([attempt])

    assert got.harness_usd == Decimal("0.50")
    assert got.gate_usd == Decimal("1")


def test_a_read_without_harness_rows_leaves_the_fact_set_figure() -> None:
    got = figures_of([AttemptRows(reads=[read("2")], fact_money=(harness_money("0.30"),))])

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (
        Decimal("2"),
        Decimal("0.30"),
        Decimal("2"),
    )


def test_an_attempt_with_nothing_adds_nothing() -> None:
    got = figures_of([AttemptRows()])

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (Decimal("0"),) * 3
    assert (got.gateway_reported, got.harness_reported) == (False, False)


def test_a_fact_money_row_without_usd_counts_as_zero() -> None:
    got = figures_of([AttemptRows(fact_money=(UsageFact(source="harness", usage_class="money"),))])

    assert (got.harness_usd, got.harness_reported) == (Decimal("0"), True)


def test_figures_is_figures_of_over_reads_only() -> None:
    reads = [[read("1", harness_money("0.5"))], [read("2", provisional=True)]]

    assert figures(reads) == figures_of(AttemptRows(reads=r) for r in reads)
