"""The Codex extractor (codex/facts)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.codex.facts import CodexLogFacts

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def _attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="done",
        harness="codex",
        model="gpt-5-codex",
    )


def _rows(facts: AttemptFacts) -> dict[str, int | None]:
    return {u.usage_class: u.tokens for u in facts.usage}


def _write(tmp_path: Path, *lines: str) -> str:
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def _turn(tmp_path: Path, extra: str = "") -> str:
    text = (FIXTURES / "turn.jsonl").read_text()
    return _write(tmp_path, text + extra)


def _usage_line(usage: str) -> str:
    return '{"type":"turn.completed","usage":' + usage + "}"


def test_the_fixture_turn_writes_the_three_token_classes() -> None:
    facts = CodexLogFacts().extract(_attempt(), str(FIXTURES / "turn.jsonl"))

    assert facts.status == "ok"
    assert facts.reason is None
    assert _rows(facts) == {"input_uncached": 300, "cache_read": 900, "output": 340}
    for row in facts.usage:
        assert (row.source, row.model, row.conversation) == ("harness", "gpt-5-codex", "main")
        assert row.subagent_type is None
        assert row.usd is None
    assert not (facts.requests or facts.activity or facts.gaps or facts.events)


def test_one_unknown_event_type_makes_the_set_partial_with_the_same_rows(tmp_path: Path) -> None:
    clean = CodexLogFacts().extract(_attempt(), str(FIXTURES / "turn.jsonl"))

    facts = CodexLogFacts().extract(_attempt(), _turn(tmp_path, '{"type":"foo"}\n'))

    assert facts.status == "partial"
    assert facts.reason == "unknown event types: foo"
    assert facts.usage == clean.usage


def test_two_unknown_event_types_are_listed_sorted(tmp_path: Path) -> None:
    text = '{"type":"foo"}\n{"type":"bar"}\n'

    facts = CodexLogFacts().extract(_attempt(), _turn(tmp_path, text))

    assert facts.reason == "unknown event types: bar, foo"


def test_interleaved_noise_leaves_the_set_ok_with_the_clean_rows() -> None:
    clean = CodexLogFacts().extract(_attempt(), str(FIXTURES / "turn.jsonl"))

    facts = CodexLogFacts().extract(_attempt(), str(FIXTURES / "interleaved.jsonl"))

    assert facts.status == "ok"
    assert facts.usage == clean.usage


def test_a_stream_without_a_usage_event_is_partial_and_writes_no_row(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"type":"thread.started","thread_id":"t"}', '{"type":"turn.started"}')

    facts = CodexLogFacts().extract(_attempt(), path)

    assert facts.status == "partial"
    assert facts.reason == "no usage event"
    assert facts.usage == ()


def test_a_turn_completed_whose_usage_is_not_a_dict_is_no_usage_event(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"type":"turn.completed","usage":"n/a"}')

    facts = CodexLogFacts().extract(_attempt(), path)

    assert (facts.status, facts.reason, facts.usage) == ("partial", "no usage event", ())


def test_a_missing_log_is_partial_and_does_not_raise(tmp_path: Path) -> None:
    facts = CodexLogFacts().extract(_attempt(), str(tmp_path / "absent.jsonl"))

    assert (facts.status, facts.reason, facts.usage) == ("partial", "no usage event", ())


def test_no_usage_and_an_unknown_type_give_both_reasons(tmp_path: Path) -> None:
    facts = CodexLogFacts().extract(_attempt(), _write(tmp_path, '{"type":"foo"}'))

    assert facts.reason == "no usage event; unknown event types: foo"


def test_only_the_last_turn_completed_counts(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _usage_line('{"input_tokens":10,"cached_input_tokens":0,"output_tokens":1}'),
        _usage_line('{"input_tokens":50,"cached_input_tokens":20,"output_tokens":7}'),
    )

    facts = CodexLogFacts().extract(_attempt(), path)

    assert _rows(facts) == {"input_uncached": 30, "cache_read": 20, "output": 7}


def test_an_absent_cached_count_writes_the_whole_input_and_no_cache_row(tmp_path: Path) -> None:
    path = _write(tmp_path, _usage_line('{"input_tokens":10,"output_tokens":4}'))

    facts = CodexLogFacts().extract(_attempt(), path)

    assert _rows(facts) == {"input_uncached": 10, "output": 4}


def test_cached_above_input_floors_the_uncached_at_zero(tmp_path: Path) -> None:
    path = _write(
        tmp_path, _usage_line('{"input_tokens":5,"cached_input_tokens":9,"output_tokens":1}')
    )

    assert _rows(CodexLogFacts().extract(_attempt(), path)) == {
        "input_uncached": 0,
        "cache_read": 9,
        "output": 1,
    }


def test_a_field_that_is_not_a_number_writes_no_row(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _usage_line('{"input_tokens":"n/a","cached_input_tokens":3,"output_tokens":"n/a"}'),
    )

    assert _rows(CodexLogFacts().extract(_attempt(), path)) == {"cache_read": 3}


def test_the_extractor_declares_no_capability_and_never_writes_money() -> None:
    extractor = CodexLogFacts()
    facts = extractor.extract(_attempt(), str(FIXTURES / "turn.jsonl"))

    assert (extractor.name, extractor.version) == ("codex", 1)
    assert not any(vars(extractor.capabilities).values())
    assert "money" not in _rows(facts)
