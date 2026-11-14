"""The OpenCode extractor (opencode/facts)."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.opencode.facts import OpenCodeLogFacts

FIXTURES = Path(__file__).parent / "fixtures" / "opencode"


def _attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="done",
        harness="opencode",
        model="qwen3",
    )


def _rows(facts: AttemptFacts) -> dict[str, int | None]:
    return {u.usage_class: u.tokens for u in facts.usage}


def _write(tmp_path: Path, *events: object) -> str:
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return str(path)


def _completed(**tokens: object) -> dict[str, object]:
    return {"type": "message.completed", "tokens": tokens}


def test_cache_read_and_write_are_stored_and_the_write_is_unsplit(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _completed(input=880, output=210, cache={"read": 120, "write": 30}),
    )

    facts = OpenCodeLogFacts().extract(_attempt(), path)

    assert facts.status == "ok"
    assert _rows(facts) == {
        "input_uncached": 880,
        "output": 210,
        "cache_read": 120,
        "cache_write_unsplit": 30,
    }
    for row in facts.usage:
        assert (row.source, row.model, row.conversation) == ("harness", "qwen3", "main")
        assert row.usd is None
    assert not (facts.requests or facts.activity or facts.gaps or facts.events)


def test_the_fixture_turn_writes_present_zeros_as_measured() -> None:
    facts = OpenCodeLogFacts().extract(_attempt(), str(FIXTURES / "turn.jsonl"))

    assert facts.status == "ok"
    assert _rows(facts) == {
        "input_uncached": 880,
        "output": 210,
        "cache_read": 0,
        "cache_write_unsplit": 0,
    }


def test_the_interleaved_fixture_is_ok_and_has_no_cache_rows() -> None:
    facts = OpenCodeLogFacts().extract(_attempt(), str(FIXTURES / "interleaved.jsonl"))

    assert facts.status == "ok"
    assert _rows(facts) == {"input_uncached": 880, "output": 210}


def test_messages_are_summed_per_class(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _completed(input=10, output=1, cache={"read": 5}),
        _completed(input=20, output=2, cache={"read": 7, "write": 3}),
        _completed(input="n/a"),
    )

    assert _rows(OpenCodeLogFacts().extract(_attempt(), path)) == {
        "input_uncached": 30,
        "output": 3,
        "cache_read": 12,
        "cache_write_unsplit": 3,
    }


def test_reasoning_and_money_are_never_written(tmp_path: Path) -> None:
    path = _write(tmp_path, _completed(input=1, output=1, reasoning=9, cache="x"))

    rows = _rows(OpenCodeLogFacts().extract(_attempt(), path))

    assert rows == {"input_uncached": 1, "output": 1}


def test_unknown_event_types_make_the_set_partial_with_the_same_rows(tmp_path: Path) -> None:
    base = [_completed(input=1, output=2)]
    clean = OpenCodeLogFacts().extract(_attempt(), _write(tmp_path, *base))

    one = OpenCodeLogFacts().extract(_attempt(), _write(tmp_path, *base, {"type": "foo"}))
    two = OpenCodeLogFacts().extract(
        _attempt(), _write(tmp_path, *base, {"type": "foo"}, {"type": "bar"})
    )

    assert (one.status, one.reason) == ("partial", "unknown event types: foo")
    assert two.reason == "unknown event types: bar, foo"
    assert one.usage == two.usage == clean.usage


def test_no_usage_event_is_partial_and_writes_no_row(tmp_path: Path) -> None:
    path = _write(
        tmp_path, {"type": "session.updated"}, {"type": "message.completed", "tokens": "x"}
    )

    facts = OpenCodeLogFacts().extract(_attempt(), path)

    assert (facts.status, facts.reason, facts.usage) == ("partial", "no usage event", ())


def test_a_missing_log_is_partial_and_does_not_raise(tmp_path: Path) -> None:
    facts = OpenCodeLogFacts().extract(_attempt(), str(tmp_path / "absent.jsonl"))

    assert (facts.status, facts.reason, facts.usage) == ("partial", "no usage event", ())


def test_the_extractor_declares_no_capability() -> None:
    extractor = OpenCodeLogFacts()

    assert (extractor.name, extractor.version) == ("opencode", 1)
    assert not any(vars(extractor.capabilities).values())
