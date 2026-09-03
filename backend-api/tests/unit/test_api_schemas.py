"""The list envelope and the money/time conventions, in one place.

`{items, next_cursor}` and nothing else; money is a 6-decimal string in USD; a timestamp
is ISO 8601 UTC ending in `Z`. These are contract decisions (Consistency Conventions —
Lists, Dates & money): the generated TypeScript in 1.3 inherits whatever these types say,
so a drift here is a drift in the browser.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from orchestrator.api.schemas.common import MoneyStr, Page, UtcTimestamp


class Item(BaseModel):
    name: str


class Cost(BaseModel):
    amount: MoneyStr


class Stamped(BaseModel):
    at: UtcTimestamp


# ── the list envelope ────────────────────────────────────────────────────────


def test_a_page_carries_exactly_items_and_next_cursor() -> None:
    assert set(Page.model_fields) == {"items", "next_cursor"}


def test_a_page_of_models_serialises_as_the_envelope() -> None:
    page = Page[Item](items=[Item(name="alpha")], next_cursor="01a0-cursor")

    assert page.model_dump() == {"items": [{"name": "alpha"}], "next_cursor": "01a0-cursor"}


def test_the_last_page_has_a_null_cursor_rather_than_omitting_it() -> None:
    """The client's loop ends on `next_cursor === null`; a missing key would be undefined."""
    page = Page[Item](items=[])

    assert page.model_dump() == {"items": [], "next_cursor": None}


def test_a_page_is_generic_over_its_item_type() -> None:
    with pytest.raises(ValidationError):
        Page[Item](items=[{"wrong": "shape"}])


def test_the_generated_schema_names_the_item_type() -> None:
    """1.3 generates one TypeScript type per parameterisation; identical names would collide."""
    schema = Page[Item].model_json_schema()

    assert "Item" in schema["title"]


# ── money ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("12.5"), "12.500000"),
        (Decimal("0"), "0.000000"),
        (Decimal("0.000001"), "0.000001"),
        (Decimal("1234.567891"), "1234.567891"),
    ],
)
def test_money_serialises_as_a_six_decimal_string(value: Decimal, expected: str) -> None:
    assert Cost(amount=value).model_dump()["amount"] == expected


def test_money_is_a_string_in_json_not_a_float() -> None:
    """A float would round a fraction-of-a-cent cost the Operator is billed for."""
    assert Cost(amount=Decimal("0.1")).model_dump_json() == '{"amount":"0.100000"}'


def test_the_generated_schema_declares_money_as_a_string() -> None:
    schema = Cost.model_json_schema(mode="serialization")

    assert schema["properties"]["amount"]["type"] == "string"


def test_money_accepts_a_decimal_string_on_the_way_in() -> None:
    assert Cost(amount=Decimal("3")).amount == Decimal("3")


def test_money_beyond_six_decimal_places_is_refused_not_silently_rounded() -> None:
    """`numeric(12,6)` is the column; a seventh decimal would be lost by the database."""
    with pytest.raises(ValidationError):
        Cost(amount=Decimal("0.0000001"))


def test_money_wider_than_the_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        Cost(amount=Decimal("1234567.000000"))


@pytest.mark.parametrize("value", ["NaN", "-NaN", "Infinity", "-Infinity", "sNaN"])
def test_a_non_finite_amount_is_a_422_not_a_500(value: str) -> None:
    """`Decimal.quantize` raises `InvalidOperation` — an `ArithmeticError`, which pydantic
    does not turn into a validation error. Non-finite values are refused before it."""
    with pytest.raises(ValidationError, match="finite"):
        Cost(amount=Decimal(value))


# ── time ─────────────────────────────────────────────────────────────────────


def test_a_utc_timestamp_serialises_with_a_trailing_z() -> None:
    stamped = Stamped(at=datetime(2026, 9, 3, 12, 0, 30, tzinfo=UTC))

    assert stamped.model_dump()["at"] == "2026-09-03T12:00:30Z"


def test_an_offset_timestamp_is_converted_to_utc() -> None:
    stamped = Stamped(at=datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))))

    assert stamped.model_dump()["at"] == "2026-09-03T12:00:00Z"


def test_microseconds_survive() -> None:
    stamped = Stamped(at=datetime(2026, 9, 3, 12, 0, 30, 123456, tzinfo=UTC))

    assert stamped.model_dump()["at"] == "2026-09-03T12:00:30.123456Z"


def test_a_naive_datetime_is_refused_not_silently_localised() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Stamped(at=datetime(2026, 9, 3, 12, 0, 30))  # noqa: DTZ001 — a naive value is the point


def test_the_generated_schema_declares_a_timestamp_as_a_string() -> None:
    schema = Stamped.model_json_schema(mode="serialization")

    assert schema["properties"]["at"]["type"] == "string"


def test_json_carries_the_z_form_too() -> None:
    stamped = Stamped(at=datetime(2026, 9, 3, 12, 0, 30, tzinfo=UTC))

    assert stamped.model_dump_json() == '{"at":"2026-09-03T12:00:30Z"}'
    assert "+00:00" not in stamped.model_dump_json()
