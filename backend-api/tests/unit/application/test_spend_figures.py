"""`gateway_read_for` row shapes and `figures` totals (story 5, owner decision T4, 2026-11-12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from orchestrator.application.use_cases.spend_figures import figures, gateway_read_for
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import GatewayRead, UsageFact
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from orchestrator.domain.ports.harness import HarnessUsage

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def an_attempt(model: str | None = "claude-opus-5") -> Attempt:
    return Attempt(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done", model=model
    )


def a_spend(usd: str, *, provisional: bool = False, capped: bool = False) -> AttemptSpend:
    models = (
        ()
        if provisional
        else (
            ModelSpend(model="gpt-5", usd=Decimal(usd), tokens_in=10, tokens_out=4),
            ModelSpend(model="mini", usd=Decimal("0"), tokens_in=1, tokens_out=1),
        )
    )
    return AttemptSpend(
        usd=Decimal(usd),
        tokens_in=11,
        tokens_out=5,
        by_model=models,
        calls=2,
        provisional=provisional,
        capped=capped,
    )


def stored(
    usd: str,
    *,
    at: int = 0,
    provisional: bool = False,
    harness: str | None = None,
) -> tuple[GatewayRead, tuple[UsageFact, ...]]:
    usage = (
        (UsageFact(source="harness", usage_class="money", usd=Decimal(harness)),)
        if harness is not None
        else ()
    )
    read = GatewayRead(
        id=new_id(),
        attempt_id=new_id(),
        run_id=new_id(),
        read_at=T0 + timedelta(minutes=at),
        trigger="attempt_end",
        provisional=provisional,
        usd=Decimal(usd),
    )
    return read, usage


def test_a_read_carries_the_answer_and_one_triple_per_model() -> None:
    attempt = an_attempt()

    read, usage = gateway_read_for(attempt, a_spend("3.5", capped=True), None, new_id(), T0)

    assert (read.attempt_id, read.run_id, read.read_at) == (attempt.id, attempt.run_id, T0)
    assert (read.trigger, read.rows, read.calls) == ("attempt_end", 2, 2)
    assert (read.provisional, read.capped, read.usd) == (False, True, Decimal("3.5"))
    assert (read.prompt, read.completion) == (11, 5)
    assert [(u.source, u.model, u.usage_class) for u in usage] == [
        ("gateway", m, c)
        for m in ("gpt-5", "mini")
        for c in ("money", "gateway_prompt", "gateway_completion")
    ]
    assert usage[0].usd == Decimal("3.5")
    assert (usage[1].tokens, usage[2].tokens) == (10, 4)


def test_harness_money_is_one_more_row_under_the_attempts_model() -> None:
    read, usage = gateway_read_for(
        an_attempt("m1"),
        a_spend("0", provisional=True),
        HarnessUsage(tokens_in=1, tokens_out=1, cost_usd=Decimal("3.00")),
        new_id(),
        T0,
    )

    assert read.provisional is True
    assert len(usage) == 1
    assert (usage[0].source, usage[0].usage_class, usage[0].model) == ("harness", "money", "m1")
    assert usage[0].usd == Decimal("3.00")


def test_gateway_only_run_gates_on_the_gateway() -> None:
    got = figures([[stored("2.00")]])

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (Decimal("2"), 0, Decimal("2"))
    assert (got.gateway_reported, got.harness_reported) == (True, False)


def test_harness_only_run_gates_on_the_harness() -> None:
    got = figures([[stored("0", provisional=True, harness="3.00")]])

    assert (got.gate_usd, got.gateway_reported, got.harness_reported) == (Decimal("3"), False, True)


def test_two_attempts_sum_and_the_higher_total_gates() -> None:
    got = figures(
        [[stored("1", harness="1.50")], [stored("2", harness="1.80")]],
    )

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (
        Decimal("3"),
        Decimal("3.30"),
        Decimal("3.30"),
    )


def test_a_gateway_total_above_the_harness_one_gates() -> None:
    assert figures([[stored("5", harness="1")]]).gate_usd == Decimal("5")


def test_the_newest_read_is_the_one_counted() -> None:
    got = figures([[stored("4", at=2), stored("1", at=1)]])

    assert got.gateway_usd == Decimal("4")


def test_a_provisional_newest_read_reports_no_gateway_money() -> None:
    got = figures([[stored("0", at=2, provisional=True), stored("9", at=1)]])

    assert (got.gateway_usd, got.gateway_reported) == (0, False)


def test_the_harness_row_comes_from_the_newest_read_that_carries_one() -> None:
    got = figures([[stored("2", at=2), stored("0", at=1, provisional=True, harness="7")]])

    assert (got.harness_usd, got.gateway_usd, got.gate_usd) == (
        Decimal("7"),
        Decimal("2"),
        Decimal("7"),
    )


def test_a_harness_row_with_no_usd_counts_as_zero() -> None:
    read, _ = stored("0", provisional=True)
    got = figures([[(read, (UsageFact(source="harness", usage_class="money"),))]])

    assert (got.harness_usd, got.harness_reported) == (0, True)


def test_nothing_reported_is_zero_with_both_flags_false() -> None:
    for reads in ([], [[]], [[stored("0", provisional=True)]]):
        got = figures(reads)

        assert (got.gate_usd, got.gateway_reported, got.harness_reported) == (0, False, False)
