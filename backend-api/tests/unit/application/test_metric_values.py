"""`MetricValue`, the missing words and `value_at` (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.values import (
    NO_SUCH_STEP,
    MetricValue,
    na,
    number,
    value_at,
    word,
)


def test_number_fills_the_method_id_and_the_figure() -> None:
    value = number("cost.gateway", "run", "run", 3, unit="USD")
    assert value.method_id == "cost.gateway@1"
    assert value.value_num == Decimal(3)
    assert value.missing is None


def test_word_holds_no_figure() -> None:
    value = word("cost.gateway", "run", "run", "not recorded")
    assert (value.value_num, value.missing) == (None, "not recorded")


def test_na_prefixes_the_reason() -> None:
    assert na("no story done") == "n/a — no story done"


def test_value_at_matches_on_scope_and_source() -> None:
    a = number("m.x", "role", "plan", 1, source="a")
    b = number("m.x", "role", "plan", 2, source="b")
    assert value_at([a, b], "m.x", "role", "plan", "b") is b
    assert value_at([a, b], "m.x", "role", "plan", "a") is a


def test_value_at_synthesizes_no_such_step() -> None:
    absent = value_at([], "cost.gateway", "role", "retro")
    assert isinstance(absent, MetricValue)
    assert (absent.missing, absent.value_num, absent.scope_key) == (NO_SUCH_STEP, None, "retro")
