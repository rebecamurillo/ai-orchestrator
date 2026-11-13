"""Token methods: harness classes, gateway tokens, recorded tokens and the cache hit share."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from orchestrator.application.metrics.methods import REGISTRY, tokens
from orchestrator.application.metrics.values import value_at
from orchestrator.domain.entities.facts import AttemptFacts, GatewayRead, UsageFact
from tests.unit.application.metrics_builders import (
    RUN_ID,
    at,
    make_ai,
    make_attempt,
    make_inputs,
    make_read,
    make_row,
)


def usage(usage_class: str, tokens_: int | None, model: str | None = "m") -> UsageFact:
    return UsageFact(
        source="harness",
        model=model,
        usage_class=usage_class,
        tokens=tokens_,  # type: ignore[arg-type]
    )


def run_value(values: list, metric: str):  # type: ignore[no-untyped-def]
    return value_at(values, metric, "run", "run")


def test_no_fact_set_reads_not_recorded_and_a_missing_class_not_available() -> None:
    row = make_row()
    bare = make_ai(row)
    held = make_ai(row, make_attempt(row, 2), facts=AttemptFacts(usage=(usage("output", 5),)))
    assert (
        run_value(REGISTRY["tokens.output@1"](make_inputs([row], [bare])), "tokens.output").missing
        == "not recorded"
    )
    values = REGISTRY["tokens.cache_read@1"](make_inputs([row], [held]))
    assert run_value(values, "tokens.cache_read").missing == "not available"


def test_cache_write_sums_the_three_write_classes() -> None:
    row = make_row()
    rows = (
        usage("cache_write_5m", 1),
        usage("cache_write_1h", 2),
        usage("cache_write_unsplit", 4),
        usage("cache_write_5m", None),
        UsageFact(source="gateway", usage_class="cache_write_5m", tokens=100),
    )
    ai = make_ai(row, facts=AttemptFacts(usage=rows))
    values = REGISTRY["tokens.cache_write@1"](make_inputs([row], [ai]))
    assert run_value(values, "tokens.cache_write").value_num == Decimal(7)


def test_a_model_scope_splits_by_the_usage_rows_model() -> None:
    row = make_row()
    rows = (usage("output", 3, "a"), usage("output", 4, None))
    values = REGISTRY["tokens.output@1"](
        make_inputs([row], [make_ai(row, facts=AttemptFacts(usage=rows))])
    )
    assert value_at(values, "tokens.output", "model", "a").value_num == Decimal(3)
    assert value_at(values, "tokens.output", "model", "m").value_num == Decimal(4)


def test_gateway_tokens_from_usage_rows_then_from_the_read() -> None:
    row = make_row()
    attempt = make_attempt(row)
    read, _ = make_read(attempt, "1", prompt=10, completion=20)
    rows = (
        UsageFact(source="gateway", model="m", usage_class="gateway_prompt", tokens=7),
        UsageFact(source="gateway", model="n", usage_class="gateway_prompt", tokens=8),
    )
    with_rows = make_ai(row, attempt, reads=((read, rows),))
    without = make_ai(row, make_attempt(row, 2), reads=((read, ()),))
    prompt = tokens.gateway_prompt(make_inputs([row], [with_rows]))
    assert run_value(prompt, "tokens.gateway_prompt").value_num == Decimal(15)
    fallback = tokens.gateway_completion(make_inputs([row], [without]))
    assert run_value(fallback, "tokens.gateway_completion").value_num == Decimal(20)


def test_gateway_tokens_missing_words() -> None:
    row = make_row()
    attempt = make_attempt(row)
    bare = make_ai(row, attempt)
    read = GatewayRead(
        id=uuid4(),
        attempt_id=attempt.id,
        run_id=RUN_ID,
        read_at=at(0),
        trigger="attempt_end",
        provisional=False,
        usd=Decimal(1),
    )
    silent = make_ai(row, make_attempt(row, 2), reads=((read, ()),))
    assert (
        run_value(
            tokens.gateway_prompt(make_inputs([row], [bare])), "tokens.gateway_prompt"
        ).missing
        == "not recorded"
    )
    assert (
        run_value(
            tokens.gateway_prompt(make_inputs([row], [silent])), "tokens.gateway_prompt"
        ).missing
        == "not available"
    )


def test_recorded_tokens_read_the_attempt_columns() -> None:
    row = make_row()
    full = make_ai(row, make_attempt(row, 1, tokens_in=5, tokens_out=6))
    bare = make_ai(row, make_attempt(row, 2))
    inputs = make_inputs([row], [full])
    assert run_value(tokens.recorded_in(inputs), "tokens.recorded_in").value_num == Decimal(5)
    assert run_value(tokens.recorded_out(inputs), "tokens.recorded_out").value_num == Decimal(6)
    assert (
        run_value(tokens.recorded_in(make_inputs([row], [bare])), "tokens.recorded_in").missing
        == "not recorded"
    )


def test_cache_hit_share_words() -> None:
    row = make_row()
    bare = make_ai(row)
    assert (
        run_value(
            tokens.cache_hit_share(make_inputs([row], [bare])), "tokens.cache_hit_share"
        ).missing
        == "not recorded"
    )
    empty = make_ai(row, make_attempt(row, 2), facts=AttemptFacts())
    assert (
        run_value(
            tokens.cache_hit_share(make_inputs([row], [empty])), "tokens.cache_hit_share"
        ).missing
        == "not available"
    )
    zero = AttemptFacts(
        usage=(usage("cache_read", 0), usage("cache_write_5m", 0), usage("input_uncached", 0))
    )
    flat = make_ai(row, make_attempt(row, 3), facts=zero)
    assert (
        run_value(
            tokens.cache_hit_share(make_inputs([row], [flat])), "tokens.cache_hit_share"
        ).missing
        == "not available"
    )
    live = AttemptFacts(
        usage=(usage("cache_read", 3), usage("cache_write_5m", 1), usage("input_uncached", 0))
    )
    share = tokens.cache_hit_share(
        make_inputs([row], [make_ai(row, make_attempt(row, 4), facts=live)])
    )
    assert run_value(share, "tokens.cache_hit_share").value_num == Decimal("0.75")
