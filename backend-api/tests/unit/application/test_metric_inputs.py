"""`choose_fact_set` and the money accessors (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from orchestrator.application.metrics.inputs import (
    AttemptInputs,
    choose_fact_set,
    gateway_usd,
    harness_rows,
    harness_usd,
)
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, UsageFact
from tests.unit.application.metrics_builders import (
    RUN_ID,
    at,
    make_ai,
    make_attempt,
    make_read,
    make_row,
)


def fact_set(status: str, seconds: int) -> FactSet:
    return FactSet(
        id=uuid4(),
        attempt_id=uuid4(),
        run_id=RUN_ID,
        extractor="x",
        extractor_version=1,
        read_at=at(seconds),
        status=status,  # type: ignore[arg-type]
    )


def test_choose_fact_set_takes_the_newest_ok_or_partial() -> None:
    old, new, failed = fact_set("ok", 1), fact_set("partial", 5), fact_set("failed", 9)
    assert choose_fact_set([old, new, failed]) is new


def test_choose_fact_set_is_none_when_none_is_usable() -> None:
    assert choose_fact_set([fact_set("failed", 1)]) is None
    assert choose_fact_set([]) is None


def test_a_settled_read_beats_a_newer_provisional_one() -> None:
    row = make_row()
    attempt = make_attempt(row)
    reads = (
        make_read(attempt, "9", provisional=True, seconds=20),
        make_read(attempt, "4", seconds=10),
        make_read(attempt, "3", seconds=5),
    )
    assert gateway_usd(make_ai(row, attempt, reads=reads)) == Decimal(4)


def test_no_settled_read_is_no_figure() -> None:
    row = make_row()
    attempt = make_attempt(row)
    only = (make_read(attempt, "9", provisional=True),)
    assert gateway_usd(make_ai(row, attempt, reads=only)) is None


def harness_money(usd: str) -> UsageFact:
    return UsageFact(source="harness", model="m", usage_class="money", usd=Decimal(usd))


def test_harness_money_comes_from_the_newest_read_that_has_any() -> None:
    row = make_row()
    attempt = make_attempt(row)
    read, _ = make_read(attempt, "1")
    facts = AttemptFacts(usage=(harness_money("7"),))
    ai = make_ai(row, attempt, facts=facts, reads=((read, (harness_money("2"),)),))
    assert harness_usd(ai) == Decimal(2)
    assert len(harness_rows(ai)) == 1


def test_harness_money_falls_back_to_the_fact_set() -> None:
    row = make_row()
    ai = make_ai(row, facts=AttemptFacts(usage=(harness_money("7"),)))
    assert harness_usd(ai) == Decimal(7)


def test_no_harness_money_is_no_figure() -> None:
    row = make_row()
    assert harness_usd(make_ai(row, facts=AttemptFacts())) is None
    assert harness_usd(make_ai(row)) is None


def test_harness_rows_fall_back_to_the_gates_fact_set_money_before_the_chosen_set() -> None:
    row = make_row()
    gate_money = (UsageFact(source="harness", usage_class="money", usd=Decimal("2")),)
    chosen = AttemptFacts(
        usage=(UsageFact(source="harness", usage_class="money", usd=Decimal("5")),)
    )
    ai = make_ai(row, facts=chosen)
    assert harness_usd(ai) == Decimal("5")
    gated = AttemptInputs(ai.attempt, row, ai.role, (), ai.fact_set, ai.facts, gate_money)
    assert harness_rows(gated) == gate_money
