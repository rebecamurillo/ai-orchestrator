"""The gateway-read comparison use case over the fixed Run (epic 2 story 6: AC1-AC3)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.gateway_comparison import gateway_comparison
from orchestrator.domain.entities.facts import GatewayRead, GatewayTrigger, UsageFact
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_fixed_run import RUN_ID, S0, S2, T0, FixedRun, build_fixed_run

ATTEMPT_COUNT = 12
CONSULT_INDEX = 11


def add_read(
    fixed: FixedRun,
    key: tuple[str, int],
    trigger: GatewayTrigger,
    usd: str,
    *,
    harness: str | None = None,
) -> None:
    attempt = fixed.attempts[key]
    usage = [UsageFact(source="gateway", model="m", usage_class="money", usd=Decimal(usd))]
    if harness is not None:
        usage.append(
            UsageFact(source="harness", model="m", usage_class="money", usd=Decimal(harness))
        )
    fixed.gateway_reads.add(
        GatewayRead(
            id=new_id(),
            attempt_id=attempt.id,
            run_id=RUN_ID,
            read_at=T0 + timedelta(days=1 if trigger == "attempt_end" else 2),
            trigger=trigger,
            rows=3,
            calls=4,
            provisional=trigger == "attempt_end",
            capped=False,
            usd=Decimal(usd),
        ),
        tuple(usage),
    )


def test_both_reads_are_listed_in_time_order_beside_the_harness_figure() -> None:
    fixed = build_fixed_run()
    key = (f"{S0}.plan", 1)
    add_read(fixed, key, "attempt_end", "0.29")
    add_read(fixed, key, "run_end", "0.58", harness="0.60")

    items = gateway_comparison(fixed.ports, RUN_ID)

    item = items[0]
    assert [(r.trigger, r.usd) for r in item.reads] == [
        ("attempt_end", Decimal("1")),
        ("attempt_end", Decimal("0.29")),
        ("run_end", Decimal("0.58")),
    ]
    assert item.harness_usd == Decimal("0.60")


def test_the_harness_figure_falls_back_to_the_first_fact_set() -> None:
    items = gateway_comparison(build_fixed_run().ports, RUN_ID)

    assert items[0].harness_usd == Decimal("1.1")


def test_no_harness_money_anywhere_is_none() -> None:
    items = gateway_comparison(build_fixed_run().ports, RUN_ID)

    assert items[-1].harness_usd is None


def test_items_follow_row_seq_then_attempt_n_with_the_role_of_each() -> None:
    fixed = build_fixed_run()

    items = gateway_comparison(fixed.ports, RUN_ID)

    assert len(items) == ATTEMPT_COUNT
    assert [(i.row_path, i.attempt_n) for i in items[1:3]] == [
        (f"{S0}.implement", 1),
        (f"{S0}.implement", 2),
    ]
    assert items[0].attempt_id == fixed.attempts[(f"{S0}.plan", 1)].id
    assert items[0].role == "plan"
    assert (items[-1].row_path, items[-1].role) == (f"{S2}.review", "senior")


def test_an_attempt_without_reads_has_an_empty_list() -> None:
    fixed = build_fixed_run()
    fixed.gateway_reads.reads.clear()  # type: ignore[attr-defined]

    items = gateway_comparison(fixed.ports, RUN_ID)

    assert all(item.reads == () for item in items)


def test_an_unknown_run_is_not_found() -> None:
    with pytest.raises(NotFound):
        gateway_comparison(build_fixed_run().ports, new_id())
