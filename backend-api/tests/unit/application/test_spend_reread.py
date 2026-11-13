"""`reread_gateway_for_run`: the gateway read again at a Run's end or a recalculation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.use_cases.spend import SpendPorts, reread_gateway_for_run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from tests.unit.application.metrics_fixed_run import RUN_ID, build_fixed_run
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway

ELEVEN = 11


def ports_of(gateway: FakeGateway) -> tuple[SpendPorts, FakeUnitOfWork]:
    fixed = build_fixed_run()
    uow = FakeUnitOfWork()
    read = fixed.ports
    return (
        SpendPorts(
            gateway=gateway,
            runs=read.runs,
            steps=read.steps,
            attempts=read.attempts,
            gateway_reads=read.gateway_reads,
            clock=read.clock,
            uow=uow,
            fact_sets=read.fact_sets,
        ),
        uow,
    )


def test_it_reads_only_harness_attempts_and_stores_the_trigger() -> None:
    gateway = FakeGateway()
    ports, uow = ports_of(gateway)
    consult = next(a for a in ports.attempts.attempts.values() if a.role == "consult")
    ports.attempts.attempts[consult.id] = consult.model_copy(update={"harness": None})

    reread_gateway_for_run(ports, RUN_ID, "recalculation")

    assert len(gateway.calls) == ELEVEN
    assert consult.id not in {attempt_id for _, attempt_id in gateway.calls}
    newest = [r for r, _ in ports.gateway_reads.reads if r.trigger == "recalculation"]
    assert len(newest) == ELEVEN
    assert uow.committed


def test_the_gate_columns_are_recomputed_and_spend_is_left_alone() -> None:
    gateway = FakeGateway()
    ports, _ = ports_of(gateway)
    attempt = next(iter(ports.attempts.attempts.values()))
    gateway.script(
        RUN_ID,
        attempt.id,
        AttemptSpend(
            usd=Decimal("9"),
            tokens_in=1,
            tokens_out=1,
            by_model=(ModelSpend(model="m", usd=Decimal("9"), tokens_in=1, tokens_out=1),),
            calls=1,
            provisional=False,
        ),
    )
    before = ports.runs.get(RUN_ID)
    assert before is not None

    updated = reread_gateway_for_run(ports, RUN_ID, "run_end")

    assert updated.gateway_spend_usd != before.gateway_spend_usd
    assert updated.spend_usd == before.spend_usd
    assert ports.runs.get(RUN_ID) == updated


def test_an_unknown_run_is_not_found() -> None:
    ports, _ = ports_of(FakeGateway())

    with pytest.raises(NotFound):
        reread_gateway_for_run(ports, new_id(), "run_end")
