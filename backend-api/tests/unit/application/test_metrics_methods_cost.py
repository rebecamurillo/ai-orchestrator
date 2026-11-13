"""Cost methods: missing words, the figure gap and cost per story done (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.methods import cost
from orchestrator.application.metrics.values import value_at
from orchestrator.domain.entities.facts import AttemptFacts, UsageFact
from tests.unit.application.metrics_builders import (
    make_ai,
    make_attempt,
    make_inputs,
    make_read,
    make_row,
)


def money(source: str, usd: str | None, model: str | None = "m") -> UsageFact:
    return UsageFact(
        source=source,  # type: ignore[arg-type]
        model=model,
        usage_class="money",
        usd=None if usd is None else Decimal(usd),
    )


def test_gateway_reading_words() -> None:
    row = make_row()
    attempt = make_attempt(row)
    assert cost.gateway_reading(make_ai(row, attempt)) == "not recorded"
    provisional = (make_read(attempt, "1", provisional=True),)
    assert cost.gateway_reading(make_ai(row, attempt, reads=provisional)) == "not available"
    assert cost.gateway_reading(make_ai(row, attempt, reads=(make_read(attempt, "2"),))) == Decimal(
        2
    )


def test_harness_reading_words() -> None:
    row = make_row()
    assert cost.harness_reading(make_ai(row)) == "not recorded"
    assert cost.harness_reading(make_ai(row, facts=AttemptFacts())) == "not available"
    paid = make_ai(row, facts=AttemptFacts(usage=(money("harness", "4"),)))
    assert cost.harness_reading(paid) == Decimal(4)


def test_gateway_by_model_reads_the_settled_reads_money_rows() -> None:
    row = make_row()
    attempt = make_attempt(row)
    read, _ = make_read(attempt, "3")
    usage = (money("gateway", "1", "a"), money("gateway", "2", None), money("gateway", None, "c"))
    ai = make_ai(row, attempt, reads=((read, usage),))
    assert cost.gateway_by_model(ai) == {"a": Decimal(1), "m": Decimal(2)}


def test_harness_by_model_falls_back_to_the_attempt_model() -> None:
    row = make_row()
    usage = (money("harness", "1", "a"), money("harness", "2", None), money("harness", None, "a"))
    ai = make_ai(row, facts=AttemptFacts(usage=usage))
    assert cost.harness_by_model(ai) == {"a": Decimal(1), "m": Decimal(2)}


def test_no_harness_money_anywhere_reads_not_available_at_run_scope() -> None:
    row = make_row()
    inputs = make_inputs([row], [make_ai(row, facts=AttemptFacts())])
    assert value_at(cost.harness(inputs), "cost.harness", "run", "run").missing == "not available"


def test_the_figure_gap_is_the_cent_difference_of_the_two_run_totals() -> None:
    row = make_row()
    attempt = make_attempt(row)
    ai = make_ai(
        row,
        attempt,
        reads=(make_read(attempt, "5.0"),),
        facts=AttemptFacts(usage=(money("harness", "4.123"),)),
    )
    gap = cost.figure_gap(make_inputs([row], [ai]))
    assert gap[0].value_num == Decimal("0.88")


def test_the_figure_gap_is_not_available_when_a_total_is_missing() -> None:
    row = make_row()
    gap = cost.figure_gap(make_inputs([row], [make_ai(row, facts=AttemptFacts())]))
    assert (gap[0].value_num, gap[0].missing) == (None, "not available")


def test_cost_per_story_done_without_a_done_story_reads_na_never_zero() -> None:
    row = make_row("stories[0].build", status="error")
    attempt = make_attempt(row)
    ai = make_ai(row, attempt, reads=(make_read(attempt, "5"),), facts=AttemptFacts())
    values = cost.per_story_done(make_inputs([row], [ai]))
    assert {v.source for v in values} == {"gateway", "harness"}
    assert all(v.missing == "n/a — no story done" and v.value_num is None for v in values)


def test_cost_per_story_done_carries_a_missing_total() -> None:
    row = make_row("stories[0].build")
    ai = make_ai(row)
    values = cost.per_story_done(make_inputs([row], [ai]))
    assert all(v.value_num is None and v.missing == "not recorded" for v in values)
