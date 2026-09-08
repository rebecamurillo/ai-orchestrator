"""`infrastructure/harness/claude/result.py`: reading a run back out of its own log.

The functions moved here out of `adapter.py` when `start`/`wait` moved in (5.4), and
`tests/unit/test_claude_adapter.py` is frozen and exercises them only through a dispatch.
This module imports the parsing module directly — which is what `scripts/check_test_pairs.py`
asks of every source module (AD-18) — and asserts the one property the whole of it exists
for: the log holds two interleaved streams, so nothing in here raises.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.infrastructure.harness.claude.result import (
    ENCODING,
    RESULT_TYPE,
    RESULT_TYPE_FIELD,
    json_objects,
    read_text,
    result_object,
    usage_from,
)

ENVELOPE = {
    RESULT_TYPE_FIELD: RESULT_TYPE,
    "total_cost_usd": 0.0342,
    "usage": {"input_tokens": 120, "output_tokens": 45},
}


def test_a_log_that_was_never_written_reads_as_nothing(tmp_path: Path) -> None:
    """A process killed before it wrote has no log, and that is not an error (AD-14)."""
    assert read_text(tmp_path / "missing.log") == ""


def test_a_log_is_read_in_the_one_encoding_and_never_fails_on_a_bad_byte(
    tmp_path: Path,
) -> None:
    log = tmp_path / "a.log"
    log.write_bytes(b"ok \xff\n")

    assert read_text(log).startswith("ok ")
    assert ENCODING == "utf-8"


def test_every_top_level_object_is_found_in_the_order_it_appears() -> None:
    text = 'npm warn\n{"a": 1}\nexporter error\n{"b": {"c": 2}}\n'

    assert json_objects(text) == [{"a": 1}, {"b": {"c": 2}}]


def test_a_nested_object_is_never_mistaken_for_a_top_level_one() -> None:
    assert json_objects('{"outer": {"inner": 1}}') == [{"outer": {"inner": 1}}]


def test_text_holding_no_object_at_all_is_an_empty_list() -> None:
    assert json_objects("plain output, then [1, 2]") == []


def test_a_brace_that_does_not_start_an_object_is_skipped() -> None:
    assert json_objects('{ not json {"a": 1}') == [{"a": 1}]


def test_the_result_envelope_wins_over_anything_printed_after_it() -> None:
    text = f"{json.dumps(ENVELOPE)}\n" + json.dumps({"error": "exporter"})

    assert result_object(text) == ENVELOPE


def test_the_last_envelope_wins_when_the_log_holds_two() -> None:
    first = {**ENVELOPE, "total_cost_usd": 0.01}
    text = f"{json.dumps(first)}\n{json.dumps(ENVELOPE)}"

    assert result_object(text) == ENVELOPE


def test_without_an_envelope_the_last_object_is_read() -> None:
    assert result_object('{"a": 1}\n{"b": 2}') == {"b": 2}


def test_a_log_with_no_object_has_no_result() -> None:
    assert result_object("nothing here") is None


def test_the_three_numbers_are_read_when_all_three_are_there() -> None:
    usage = usage_from(ENVELOPE)

    assert usage is not None
    assert (usage.tokens_in, usage.tokens_out) == (120, 45)
    assert usage.cost_usd == Decimal("0.0342")


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"usage": "n/a", "total_cost_usd": 1},
        {"usage": {"input_tokens": 1, "output_tokens": 2}},
        {"usage": {"input_tokens": True, "output_tokens": 2}, "total_cost_usd": 1},
        {"usage": {"input_tokens": 1, "output_tokens": 2}, "total_cost_usd": "n/a"},
        {"usage": {"output_tokens": 2}, "total_cost_usd": 1},
    ],
    ids=[
        "no result",
        "no usage key",
        "usage is not an object",
        "no cost",
        "a boolean token count",
        "a cost that is not a number",
        "a missing token count",
    ],
)
def test_anything_short_of_all_three_reports_no_usage_and_never_raises(
    result: dict[str, object] | None,
) -> None:
    """A cost read as zero would be read back as measured; `None` is the honest answer."""
    assert usage_from(result) is None


def test_a_cost_given_as_a_string_of_digits_is_still_a_decimal() -> None:
    usage = usage_from({**ENVELOPE, "total_cost_usd": "0.5"})

    assert usage is not None
    assert usage.cost_usd == Decimal("0.5")
