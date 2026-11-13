"""`record_attempt_spend` stores a gateway read per call and recomputes the Run's five figures
from stored reads (story 5, owner decision T4, 2026-11-12)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.rules import budget
from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from orchestrator.domain.ports.harness import HarnessUsage
from tests.unit.application.test_record_attempt_spend import Harness, a_row, a_run, an_attempt
from tests.unit.fakes.facts import FakeGatewayReadRepository


def settled(usd: str, *, capped: bool = False) -> AttemptSpend:
    return AttemptSpend(
        usd=Decimal(usd),
        tokens_in=100,
        tokens_out=50,
        by_model=(ModelSpend(model="gpt-5", usd=Decimal(usd), tokens_in=100, tokens_out=50),),
        calls=1,
        provisional=False,
        capped=capped,
    )


PROVISIONAL = AttemptSpend(
    usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
)


def usage(usd: str) -> HarnessUsage:
    return HarnessUsage(tokens_in=7, tokens_out=3, cost_usd=Decimal(usd))


class World:
    def __init__(self, **run_fields: object) -> None:
        self.h = Harness()
        self.reads = FakeGatewayReadRepository()
        self.run: Run = a_run(**run_fields)
        self.h.runs.add(self.run)
        self.row = a_row(self.run, seq=0)
        self.h.steps.add_many([self.row])

    def attempt(self, n: int = 1) -> Attempt:
        attempt = an_attempt(self.row, self.run, n=n, model="claude-opus-5")
        self.h.attempts.add(attempt)
        return attempt

    def record(self, attempt: Attempt, spend: AttemptSpend, harness: HarnessUsage | None) -> Run:
        self.h.gateway.script(self.run.id, attempt.id, spend)
        ports = self.h.ports()
        object.__setattr__(ports, "gateway_reads", self.reads)
        return record_attempt_spend(ports, self.run, attempt, harness)


def test_gateway_below_harness_parks_on_the_harness_figure() -> None:
    world = World(budget_usd=Decimal("10.25"))

    run = world.record(world.attempt(), settled("10.00"), usage("10.50"))

    park = budget.check(run)
    assert park is not None
    assert park.reason == "budget $10.50 / $10.25"


def test_a_disabled_gateway_leaves_the_harness_money_as_the_gate() -> None:
    world = World()

    run = world.record(world.attempt(), PROVISIONAL, usage("3.00"))

    assert (run.gate_spend_usd, run.harness_reported, run.gateway_reported) == (
        Decimal("3.00"),
        True,
        False,
    )


def test_an_attempt_without_harness_usage_gates_on_the_gateway() -> None:
    world = World()

    run = world.record(world.attempt(), settled("2.00"), None)

    assert (run.gate_spend_usd, run.gateway_reported, run.harness_reported) == (
        Decimal("2.00"),
        True,
        False,
    )


def test_two_attempts_sum_and_a_replay_changes_nothing() -> None:
    world = World()
    first, second = world.attempt(1), world.attempt(2)
    world.record(first, settled("1"), usage("1.50"))
    run = world.record(second, settled("2"), usage("1.80"))
    world.run = run

    again = world.record(second, settled("2"), usage("1.80"))

    for got in (run, again):
        assert (got.gateway_spend_usd, got.harness_spend_usd, got.gate_spend_usd) == (
            Decimal("3"),
            Decimal("3.30"),
            Decimal("3.30"),
        )
    assert len(world.reads.reads) == 3  # noqa: PLR2004


def test_each_call_stores_one_read_with_its_capped_flag_and_usage_rows() -> None:
    world = World()
    attempt = world.attempt()

    world.record(attempt, settled("2", capped=True), usage("2.5"))

    ((read, rows),) = world.reads.reads
    assert (read.attempt_id, read.trigger, read.capped, read.usd) == (
        attempt.id,
        "attempt_end",
        True,
        Decimal("2"),
    )
    assert [(u.source, u.usage_class) for u in rows] == [
        ("gateway", "money"),
        ("gateway", "gateway_prompt"),
        ("gateway", "gateway_completion"),
        ("harness", "money"),
    ]
    assert world.reads.usage(read.id) == rows


def test_the_attempt_and_run_spend_columns_are_what_they_were() -> None:
    world = World()
    attempt = world.attempt()

    run = world.record(attempt, settled("3.50"), usage("9"))

    stored = world.h.attempts.attempts[attempt.id]
    assert (stored.cost_usd, stored.tokens_in, stored.tokens_out) == (Decimal("3.50"), 100, 50)
    assert stored.cost_provisional is False
    assert (run.spend_usd, run.spend_provisional) == (Decimal("3.50"), False)


def test_a_provisional_attempt_keeps_its_old_cost_columns() -> None:
    world = World()
    attempt = world.attempt()

    run = world.record(attempt, PROVISIONAL, usage("3"))

    stored = world.h.attempts.attempts[attempt.id]
    assert (stored.cost_usd, stored.cost_provisional) == (Decimal("3"), True)
    assert (run.spend_usd, run.spend_provisional) == (Decimal("3"), True)
