"""Reading an `opencode run --format json` stream back (AD-10, AD-11, story 7.3).

The sibling of `tests/unit/test_codex_events.py`: same two facts read out of a stream that
also holds stderr — the session and the tokens — and the same rule that neither is ever an
exception. What differs is the harness's own framing, and every name of it is **provisional**
until story 7.4 has run the real CLI at `OPENCODE_VERSION` (`addendum.md` §B). These tests
therefore pin the *documented shape* and, more importantly, the behaviour around it:

- the first `sessionID` wins, and a stream that names none answers `None`;
- an object is found even with a warning glued to the front of its line, because the log
  holds stdout and stderr interleaved by construction (`jsonl.json_objects`);
- tokens are read both-or-neither, so a half-reported turn is `usage=None` rather than a
  zero that would be read back as measured;
- the cost is `0` and that is **not** provisional: PRD §11 records a local model at zero cost
  with its tokens, which is the whole point of the `local` harness as a cost lever.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.infrastructure.harness.jsonl import read_text
from orchestrator.infrastructure.harness.opencode.events import (
    STREAM_COST_USD,
    events,
    result_object,
    session_id_from,
    usage_from,
)

FIXTURES = Path(__file__).parent / "infrastructure" / "harness" / "fixtures" / "opencode"
SESSION_ID = "ses_7f3c1a0b9d2e4f5a"
TOKENS_IN = 880
TOKENS_OUT = 210


def stream_of(name: str) -> list[dict[str, object]]:
    return events(read_text(FIXTURES / f"{name}.jsonl"))


# ── the session ──────────────────────────────────────────────────────────────


def test_the_session_is_the_first_one_the_stream_names() -> None:
    assert session_id_from(stream_of("turn")) == SESSION_ID


def test_a_stream_that_names_no_session_answers_none() -> None:
    """Not an exception: the store fallback is the adapter's next question, and a run that
    left neither is an attempt with no session rather than a failed read."""
    assert session_id_from(stream_of("no-session")) is None


def test_a_session_is_found_with_warnings_interleaved_around_it() -> None:
    """stdout and stderr share the log file by construction (AD-10, `jsonl.py`)."""
    assert session_id_from(stream_of("interleaved")) == SESSION_ID


def test_an_empty_stream_answers_none() -> None:
    assert session_id_from(events("")) is None


def test_a_non_string_session_field_is_not_a_session() -> None:
    assert session_id_from(events('{"sessionID": 17}')) is None


def test_an_empty_session_field_is_not_a_session() -> None:
    assert session_id_from(events('{"sessionID": ""}')) is None


# ── the result object ────────────────────────────────────────────────────────


def test_the_result_is_the_last_object_that_reports_tokens() -> None:
    """The last object of any kind is only the fallback: an exporter that fails on shutdown
    prints its own JSON after the turn ended, and taking whatever printed last would report
    no usage for a run that reported usage."""
    result = result_object(stream_of("interleaved"))

    assert result is not None
    assert result["tokens"] == {"input": TOKENS_IN, "output": TOKENS_OUT}


def test_the_result_falls_back_to_the_last_object_when_nothing_reports_tokens() -> None:
    stream = events('{"type":"one"}\n{"type":"two"}')

    assert result_object(stream) == {"type": "two"}


def test_a_stream_with_no_json_at_all_has_no_result() -> None:
    assert result_object(events("npm warn deprecated")) is None


# ── the usage ────────────────────────────────────────────────────────────────


def test_the_tokens_are_read_from_the_turn_that_reported_them() -> None:
    usage = usage_from(result_object(stream_of("turn")))

    assert usage is not None
    assert (usage.tokens_in, usage.tokens_out) == (TOKENS_IN, TOKENS_OUT)


def test_a_local_model_is_recorded_at_zero_cost_with_its_tokens() -> None:
    """PRD §11 — the one figure in this module that is not provisional."""
    usage = usage_from(result_object(stream_of("turn")))

    assert usage is not None
    assert usage.cost_usd == Decimal("0")
    assert STREAM_COST_USD == Decimal("0")


def test_a_half_reported_turn_is_no_usage_at_all() -> None:
    """Both or neither: a zero written into `tokens_in` would be read back as measured."""
    assert usage_from({"tokens": {"input": 12}}) is None


def test_a_turn_that_reported_no_tokens_envelope_is_no_usage() -> None:
    assert usage_from({"type": "message.completed"}) is None


def test_a_non_numeric_token_count_is_no_usage() -> None:
    assert usage_from({"tokens": {"input": "n/a", "output": 3}}) is None


def test_no_result_object_is_no_usage() -> None:
    assert usage_from(None) is None
