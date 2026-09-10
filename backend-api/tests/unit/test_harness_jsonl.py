"""`infrastructure/harness/jsonl.py`: the tolerant primitives every adapter reads a log with.

They were `claude/result.py`'s until 7.1 needed the same three things for a second harness —
find the top-level JSON objects in a file that holds two interleaved streams, and turn a field
that may not be a number into a number or into nothing. Sharing them rather than copying them
is what keeps "a log is never an exception" one rule instead of one rule per harness.

`claude/result.py` re-exports every name it used to define, so this module asserts the
behaviour and `tests/unit/test_claude_result_parsing.py` (frozen) still asserts it through the
old import path — which is the proof that the move preserved them.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.infrastructure.harness import jsonl

# ── read_text ────────────────────────────────────────────────────────────────


def test_a_log_that_was_never_written_reads_as_nothing(tmp_path: Path) -> None:
    assert jsonl.read_text(tmp_path / "missing.log") == ""


def test_a_directory_is_not_a_log_either(tmp_path: Path) -> None:
    assert jsonl.read_text(tmp_path) == ""


def test_an_undecodable_byte_is_replaced_rather_than_raised(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_bytes(b'{"type": "x"}\n\xff\n')

    assert '{"type": "x"}' in jsonl.read_text(log)


def test_the_encoding_is_the_one_every_adapter_writes_in() -> None:
    assert jsonl.ENCODING == "utf-8"


# ── json_objects ─────────────────────────────────────────────────────────────


def test_every_top_level_object_is_found_in_order() -> None:
    text = '{"n": 1}\n{"n": 2}\n{"n": 3}\n'

    assert [item["n"] for item in jsonl.json_objects(text)] == [1, 2, 3]


def test_text_around_the_objects_is_skipped_rather_than_failing() -> None:
    text = 'npm warn something\n{"n": 1}\n{ not json }\n{"n": 2}\n'

    assert [item["n"] for item in jsonl.json_objects(text)] == [1, 2]


def test_a_nested_object_is_not_mistaken_for_a_top_level_one() -> None:
    text = '{"outer": {"inner": 1}}\n'

    assert jsonl.json_objects(text) == [{"outer": {"inner": 1}}]


def test_a_json_array_is_not_an_object() -> None:
    assert jsonl.json_objects("[1, 2, 3]\n") == []


def test_no_json_at_all_is_an_empty_list() -> None:
    assert jsonl.json_objects("Error: could not reach the gateway\n") == []


# ── objects_with ─────────────────────────────────────────────────────────────


def test_objects_with_selects_by_one_field_and_keeps_the_order() -> None:
    objects = [{"type": "a", "n": 1}, {"type": "b"}, {"type": "a", "n": 2}]

    assert [item["n"] for item in jsonl.objects_with(objects, "type", "a")] == [1, 2]


def test_objects_with_ignores_an_entry_that_does_not_carry_the_field() -> None:
    assert jsonl.objects_with([{"other": "a"}], "type", "a") == []


# ── as_int / as_decimal ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [(12, 12), (12.9, 12), ("12", 12)],
    ids=["int", "float", "numeric string"],
)
def test_a_token_count_is_read_from_whatever_json_shape_carried_it(
    value: object, expected: int
) -> None:
    assert jsonl.as_int(value) == expected


@pytest.mark.parametrize(
    "value",
    [True, False, None, "many", {"n": 1}, [1]],
    ids=["true", "false", "none", "word", "object", "array"],
)
def test_a_token_count_that_is_not_a_number_is_nothing_rather_than_an_exception(
    value: object,
) -> None:
    """`bool` is rejected explicitly: `True` tokens is a reading error, not one token."""
    assert jsonl.as_int(value) is None


def test_an_amount_is_a_decimal_and_never_a_float() -> None:
    amount = jsonl.as_decimal(0.0342)

    assert amount == Decimal("0.0342")
    assert isinstance(amount, Decimal)


@pytest.mark.parametrize(
    "value",
    [True, None, "n/a", {"usd": 1}, [1]],
    ids=["bool", "none", "word", "object", "array"],
)
def test_an_amount_that_is_not_one_is_nothing_rather_than_an_exception(value: object) -> None:
    assert jsonl.as_decimal(value) is None
