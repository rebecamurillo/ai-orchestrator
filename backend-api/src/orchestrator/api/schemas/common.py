"""The conventions every payload of this API inherits (Consistency Conventions).

Three decisions live here so no endpoint re-takes them:

- **Lists** are `{items, next_cursor}` and nothing else. There is no envelope anywhere else.
- **Money** is USD, `numeric(12,6)` in the database, and a decimal *string* in JSON. A JSON
  number would be an IEEE double, and a fraction-of-a-cent model cost is exactly the value
  that loses digits there.
- **Timestamps** are ISO 8601 UTC ending in `Z`. A naive datetime is refused rather than
  guessed at, because the guess would be the server's local zone.

The generated contract (AD-3) is derived from these types, so the browser sees the same
rules without anyone restating them in TypeScript.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, PlainSerializer

#: `numeric(12,6)`: at most 12 significant digits, exactly 6 of them after the point.
MONEY_SCALE = Decimal("0.000001")
MONEY_DIGITS = 12


class Page[T](BaseModel):
    """The one list envelope. `next_cursor` is `null` on the last page, never absent."""

    items: list[T]
    next_cursor: str | None = None


def _as_money(value: Decimal) -> Decimal:
    """Refuse anything `numeric(12,6)` cannot hold, instead of rounding it away silently.

    Every refusal is a `ValueError`, which pydantic reports as a 422. `Decimal.quantize`
    raises `decimal.InvalidOperation` on `NaN` and `Infinity` — an `ArithmeticError`, which
    pydantic does not catch, so a non-finite amount would leave as a 500 instead.
    """
    if not value.is_finite():
        raise ValueError(f"money must be a finite amount, got {value}")
    quantised = value.quantize(MONEY_SCALE)
    if quantised != value:
        raise ValueError(f"money has at most 6 decimal places, got {value}")
    if len(quantised.as_tuple().digits) > MONEY_DIGITS:
        raise ValueError(f"money has at most {MONEY_DIGITS} digits, got {value}")
    return quantised


def _money_string(value: Decimal) -> str:
    """`Decimal("12.5")` -> `"12.500000"` — the same digits the column holds."""
    return f"{value:.6f}"


def _as_utc(value: datetime) -> datetime:
    """Refuse a naive datetime; convert an offset one to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("a timestamp must be timezone-aware, and is stored as UTC")
    return value.astimezone(UTC)


def _iso_z(value: datetime) -> str:
    """`2026-09-03T12:00:30+00:00` -> `2026-09-03T12:00:30Z`, the form the UI parses."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


MoneyStr = Annotated[
    Decimal,
    AfterValidator(_as_money),
    PlainSerializer(_money_string, return_type=str),
]

UtcTimestamp = Annotated[
    datetime,
    AfterValidator(_as_utc),
    PlainSerializer(_iso_z, return_type=str),
]
