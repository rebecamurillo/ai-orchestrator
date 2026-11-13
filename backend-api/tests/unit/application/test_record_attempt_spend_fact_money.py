"""AC5 (story 6): a migrated provisional attempt's harness money counts in the harness and
gate totals of every later `record_attempt_spend`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, UsageFact
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from tests.unit.application.test_record_attempt_spend import Harness, a_row, a_run, an_attempt
from tests.unit.fakes.facts import FakeFactSetRepository, FakeGatewayReadRepository

SETTLED = AttemptSpend(
    usd=Decimal("1.00"),
    tokens_in=10,
    tokens_out=5,
    by_model=(ModelSpend(model="gpt-5", usd=Decimal("1.00"), tokens_in=10, tokens_out=5),),
    calls=1,
    provisional=False,
)


def world(*, with_fact_sets: bool) -> tuple[Harness, FakeFactSetRepository]:
    h = Harness()
    fact_sets = FakeFactSetRepository()
    run = a_run()
    h.runs.add(run)
    row = a_row(run, seq=0)
    h.steps.add_many([row])
    old = an_attempt(row, run, n=1, cost_usd=Decimal("0.30"), cost_provisional=True)
    new = an_attempt(row, run, n=2, model="gpt-5")
    h.attempts.add(old)
    h.attempts.add(new)
    fact_sets.add(
        FactSet(
            id=new_id(),
            attempt_id=old.id,
            run_id=run.id,
            extractor="migrated",
            extractor_version=1,
            read_at=datetime(2026, 11, 13, tzinfo=UTC),
            status="partial",
        ),
        AttemptFacts(
            status="partial",
            usage=(UsageFact(source="harness", usage_class="money", usd=Decimal("0.30")),),
        ),
    )
    h.gateway.script(run.id, new.id, SETTLED)
    h.run, h.new = run, new  # type: ignore[attr-defined]
    return h, fact_sets


def record(h: Harness, fact_sets: FakeFactSetRepository | None):  # type: ignore[no-untyped-def]
    ports = h.ports()
    object.__setattr__(ports, "gateway_reads", FakeGatewayReadRepository())
    object.__setattr__(ports, "fact_sets", fact_sets)
    return record_attempt_spend(ports, h.run, h.new, None)  # type: ignore[attr-defined]


def test_a_migrated_provisional_attempt_counts_in_the_gate() -> None:
    h, fact_sets = world(with_fact_sets=True)

    run = record(h, fact_sets)

    assert run.harness_spend_usd == Decimal("0.30")
    assert run.gateway_spend_usd == Decimal("1.00")
    assert run.gate_spend_usd == Decimal("1.30")


def test_without_the_fact_set_port_the_totals_are_story_5s() -> None:
    h, _ = world(with_fact_sets=False)

    run = record(h, None)

    assert (run.harness_spend_usd, run.gate_spend_usd) == (Decimal("0"), Decimal("1.00"))


def test_a_fact_set_without_harness_money_is_skipped() -> None:
    h, fact_sets = world(with_fact_sets=True)
    old = next(iter(fact_sets.sets))
    fact_sets.add(
        old.model_copy(update={"id": new_id(), "extractor": "claude"}),
        AttemptFacts(usage=(UsageFact(source="gateway", usage_class="money"),)),
    )
    fact_sets.sets.reverse()

    run = record(h, fact_sets)

    assert run.harness_spend_usd == Decimal("0.30")
