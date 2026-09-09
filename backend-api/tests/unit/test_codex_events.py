"""`infrastructure/harness/codex/events.py`: what a `codex exec --json` stream is read for.

Two facts and nothing else (AD-10): the session this attempt ran under, and the tokens the
harness itself reported. Both come out of the stream's *own framing* — the event type and the
usage envelope — never out of anything the model wrote.

**Every name asserted here is provisional.** The event name, its id field, the completion event
and its usage fields are the shapes `briefs/7-1-codex-adapter.md` documents with `[verify]`
markers against them; story 7.2 settles them against the real CLI. What this module pins is the
*behaviour around* them, which does not change when a name does: an absent event is `None` and
never an exception, a partial usage envelope is `None` rather than a zero read back as measured,
and the completion object is handed on whole.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.infrastructure.harness.codex import events as codex_events

FIXTURES = Path(__file__).parent / "infrastructure" / "harness" / "fixtures" / "codex"
SESSION_ID = "0199c4a1-6d2e-7f31-8a44-51b6c7d8e9f0"
TOKENS_IN = 1200
TOKENS_OUT = 340


def stream(name: str) -> list[dict[str, object]]:
    return codex_events.events(FIXTURES.joinpath(name).read_text(encoding="utf-8"))


# ── the fixtures are the shape the brief documents ───────────────────────────


def test_the_sample_stream_is_read_as_its_own_events() -> None:
    assert [item["type"] for item in stream("turn.jsonl")] == [
        codex_events.THREAD_STARTED,
        "turn.started",
        "item.completed",
        "item.completed",
        codex_events.TURN_COMPLETED,
    ]


# ── the session ──────────────────────────────────────────────────────────────


def test_the_session_is_the_id_the_thread_event_carries() -> None:
    assert codex_events.session_id_from(stream("turn.jsonl")) == SESSION_ID


def test_a_stream_without_the_thread_event_names_no_session() -> None:
    """7.2's readiness line `session id recorded` is what fails on this; nothing raises."""
    assert codex_events.session_id_from(stream("no-thread.jsonl")) is None


def test_the_event_is_found_among_whatever_else_shared_the_file() -> None:
    """stdout and stderr land in one log, so the stream is never alone in it."""
    assert codex_events.session_id_from(stream("interleaved.jsonl")) == SESSION_ID


def test_a_thread_event_with_no_id_names_no_session() -> None:
    assert codex_events.session_id_from([{"type": codex_events.THREAD_STARTED}]) is None


def test_an_id_that_is_not_text_names_no_session() -> None:
    assert (
        codex_events.session_id_from(
            [{"type": codex_events.THREAD_STARTED, codex_events.THREAD_ID: 7}]
        )
        is None
    )


def test_an_empty_id_names_no_session() -> None:
    assert (
        codex_events.session_id_from(
            [{"type": codex_events.THREAD_STARTED, codex_events.THREAD_ID: ""}]
        )
        is None
    )


def test_the_first_thread_event_wins_when_a_resumed_stream_carries_two() -> None:
    """A resumed turn reopens the thread; the id is the same one either way, and taking the
    first is what makes that true of a stream where a later event carried a different one."""
    first = {"type": codex_events.THREAD_STARTED, codex_events.THREAD_ID: SESSION_ID}
    second = {"type": codex_events.THREAD_STARTED, codex_events.THREAD_ID: "later"}

    assert codex_events.session_id_from([first, second]) == SESSION_ID


# ── the completion object ────────────────────────────────────────────────────


def test_the_completion_object_is_the_turn_event_and_is_handed_on_whole() -> None:
    result = codex_events.result_object(stream("turn.jsonl"))

    assert result == {
        "type": codex_events.TURN_COMPLETED,
        "usage": {
            "input_tokens": TOKENS_IN,
            "cached_input_tokens": 900,
            "output_tokens": TOKENS_OUT,
        },
    }


def test_a_completion_event_is_preferred_over_whatever_printed_last() -> None:
    """An exporter that fails on shutdown prints its own JSON after the turn completed."""
    result = codex_events.result_object(stream("interleaved.jsonl"))

    assert result is not None
    assert result["type"] == codex_events.TURN_COMPLETED


def test_a_stream_with_no_completion_event_falls_back_to_the_last_object() -> None:
    objects = [{"type": "turn.started"}, {"type": "turn.failed", "error": "gateway"}]

    assert codex_events.result_object(objects) == objects[-1]


def test_no_objects_at_all_is_no_completion_object() -> None:
    assert codex_events.result_object([]) is None


# ── the usage ────────────────────────────────────────────────────────────────


def test_the_tokens_are_read_and_the_cost_is_left_to_the_gateway() -> None:
    """AD-11: Codex's own stream reports tokens and no money, and the Gateway's spend log is
    what settles the amount — so the harness's figure is zero and `cost_provisional` stays."""
    usage = codex_events.usage_from(codex_events.result_object(stream("turn.jsonl")))

    assert usage is not None
    assert usage.tokens_in == TOKENS_IN
    assert usage.tokens_out == TOKENS_OUT
    assert usage.cost_usd == Decimal("0")


def test_no_completion_object_is_no_usage() -> None:
    assert codex_events.usage_from(None) is None


@pytest.mark.parametrize(
    "result",
    [
        {"type": "turn.completed"},
        {"type": "turn.completed", "usage": "not an object"},
        {"type": "turn.completed", "usage": {"input_tokens": 1}},
        {"type": "turn.completed", "usage": {"output_tokens": 1}},
        {"type": "turn.completed", "usage": {"input_tokens": "many", "output_tokens": 1}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": True}},
    ],
    ids=[
        "no usage",
        "usage is not an object",
        "no output tokens",
        "no input tokens",
        "tokens are not a number",
        "tokens are a bool",
    ],
)
def test_a_partial_usage_envelope_is_no_usage_at_all(result: dict[str, object]) -> None:
    """AD-11: `tokens_in`/`tokens_out` written as zero would be read back as measured."""
    assert codex_events.usage_from(result) is None


def test_a_stream_is_read_from_text_the_same_way_a_log_is() -> None:
    text = "\n".join(json.dumps(item) for item in stream("turn.jsonl"))

    assert codex_events.session_id_from(codex_events.events(text)) == SESSION_ID
