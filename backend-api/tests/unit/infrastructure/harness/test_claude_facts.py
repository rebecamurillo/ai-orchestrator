"""The Claude extractor over the committed fixture and synthetic streams (story 1.3)."""

# ruff: noqa: PLR2004, PLR0913, PLR0917

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import facts as registry
from orchestrator.infrastructure.harness.claude.facts import (
    DEFAULT_TEST_RUN_PATTERNS,
    NO_MODEL_USAGE,
    ClaudeLogFacts,
)
from orchestrator.infrastructure.harness.facts import RedactingLogFacts, build_log_facts
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue
from orchestrator.infrastructure.settings import Settings

FIXTURE = Path(__file__).parents[2] / "fixtures" / "claude_attempt_log.jsonl"
SUB = "toolu_01KJ3HvMMdUbXf7C6Zcp9am7"
MODEL = "claude-opus-5-5"


def _attempt() -> Attempt:
    return Attempt(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done", harness="claude"
    )


def _extract(path: Path) -> AttemptFacts:
    return ClaudeLogFacts().extract(_attempt(), str(path))


@pytest.fixture(scope="module")
def fixture_facts() -> AttemptFacts:
    return _extract(FIXTURE)


def _sum(facts: AttemptFacts, usage_class: str) -> int:
    return sum(
        u.tokens or 0
        for u in facts.usage
        if u.source == "harness" and u.model == MODEL and u.usage_class == usage_class
    )


def test_the_fixture_reads_as_ok(fixture_facts: AttemptFacts) -> None:
    assert fixture_facts.status == "ok"
    assert fixture_facts.reason is None
    assert ClaudeLogFacts.capabilities.per_request_usage is True


def test_usage_classes_sum_to_the_model_usage_table(fixture_facts: AttemptFacts) -> None:
    assert _sum(fixture_facts, "input_uncached") == 108
    assert _sum(fixture_facts, "cache_read") == 4_310_425
    assert _sum(fixture_facts, "cache_write_5m") == 119_286
    assert _sum(fixture_facts, "cache_write_1h") == 109_642
    assert _sum(fixture_facts, "output") == 42_963
    assert _sum(fixture_facts, "thinking") == 22_576
    assert not [u for u in fixture_facts.usage if u.usage_class == "cache_write_unsplit"]


def test_input_classes_are_split_by_conversation_and_the_rest_is_attempt_wide(
    fixture_facts: AttemptFacts,
) -> None:
    by_class: dict[str, list[Any]] = defaultdict(list)
    for u in fixture_facts.usage:
        by_class[u.usage_class].append(u)
    for name in ("input_uncached", "cache_read", "cache_write_5m", "cache_write_1h"):
        rows = {u.conversation: u for u in by_class[name]}
        assert set(rows) == {"main", SUB}
        assert rows["main"].subagent_type is None
        assert rows[SUB].subagent_type == "general-purpose"
    for name in ("output", "thinking", "money"):
        assert len(by_class[name]) == 1
        assert by_class[name][0].conversation is None
        assert by_class[name][0].subagent_type is None


def test_the_money_row_is_the_cost_usd_of_the_model(fixture_facts: AttemptFacts) -> None:
    money = [u for u in fixture_facts.usage if u.usage_class == "money"]
    assert len(money) == 1
    assert money[0].source == "harness"
    assert money[0].model == MODEL
    assert money[0].tokens is None
    assert money[0].usd is not None
    assert abs(money[0].usd - Decimal("3.195343000000001")) < Decimal("1e-9")


def test_conversations_messages_and_gaps(fixture_facts: AttemptFacts) -> None:
    gaps = {g.conversation: g for g in fixture_facts.gaps}
    assert set(gaps) == {"main", SUB}
    assert gaps["main"].messages == 21
    assert gaps["main"].gaps_s == (86, 217)
    assert gaps[SUB].messages == 33
    assert gaps[SUB].gaps_s == ()


def test_calls_per_tool_per_conversation_and_errors(fixture_facts: AttemptFacts) -> None:
    calls = {(a.conversation, a.tool): a.calls for a in fixture_facts.activity}
    assert calls == {
        ("main", "Bash"): 13,
        ("main", "Write"): 2,
        ("main", "Skill"): 1,
        ("main", "Read"): 1,
        ("main", "Agent"): 1,
        ("main", "ToolSearch"): 1,
        (SUB, "Bash"): 32,
        (SUB, "Skill"): 1,
    }
    errors = {(a.conversation, a.tool): a.errors for a in fixture_facts.activity if a.errors}
    assert errors == {("main", "Bash"): 1}


def test_files_read_edited_and_test_runs(fixture_facts: AttemptFacts) -> None:
    assert sum(a.files_read for a in fixture_facts.activity) == 1
    assert sum(a.files_edited for a in fixture_facts.activity) == 2
    assert sum(a.test_runs for a in fixture_facts.activity) == 1
    bash = next(a for a in fixture_facts.activity if (a.conversation, a.tool) == ("main", "Bash"))
    assert bash.test_runs == 1


def test_write_and_test_run_events(fixture_facts: AttemptFacts) -> None:
    writes = [e for e in fixture_facts.events if e.kind == "write"]
    assert sorted(e.at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" for e in writes) == [
        "2026-11-12T09:58:22.868Z",
        "2026-11-12T09:58:28.161Z",
    ]
    assert all(e.path for e in writes)
    runs = [e for e in fixture_facts.events if e.kind == "test_run"]
    assert len(runs) == 1
    assert runs[0].conversation == "main"
    assert runs[0].exit_code is None
    assert runs[0].at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] == "2026-11-12T09:51:37.323"
    assert runs[0].command is not None
    assert "make test" in runs[0].command


def test_per_request_usage(fixture_facts: AttemptFacts) -> None:
    rows = fixture_facts.requests
    assert len(rows) == 54
    assert len({r.message_id for r in rows}) == 54
    assert sum(r.input_uncached for r in rows) == 108
    assert sum(r.cache_read for r in rows) == 4_310_425
    assert sum(r.cache_write_5m for r in rows) == 119_286
    assert sum(r.cache_write_1h for r in rows) == 109_642
    assert sum(r.output for r in rows) == 459


# ---- synthetic streams -------------------------------------------------------------------


def _usage(inp: int = 1, read: int = 2, w5: int = 3, w1: int = 4, out: int = 5) -> dict[str, Any]:
    return {
        "input_tokens": inp,
        "cache_read_input_tokens": read,
        "cache_creation": {
            "ephemeral_5m_input_tokens": w5,
            "ephemeral_1h_input_tokens": w1,
        },
        "output_tokens": out,
    }


def _assistant(
    mid: str,
    ts: str | None,
    blocks: list[dict[str, Any]] | None = None,
    parent: str | None = None,
    usage: dict[str, Any] | None = None,
    model: str = "m1",
) -> dict[str, Any]:
    message: dict[str, Any] = {"id": mid, "model": model, "content": blocks or []}
    if usage is not None:
        message["usage"] = usage
    event: dict[str, Any] = {"type": "assistant", "message": message, "parent_tool_use_id": parent}
    if ts is not None:
        event["timestamp"] = ts
    return event


def _call(cid: str, name: str, **inp: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": cid, "name": name, "input": inp}


def _result(*pairs: tuple[str, Any], parent: str | None = None) -> dict[str, Any]:
    blocks = [
        {"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": "x"}
        for tid, err in pairs
    ]
    return {"type": "user", "message": {"content": blocks}, "parent_tool_use_id": parent}


def _final(model_usage: dict[str, Any] | None) -> dict[str, Any]:
    event: dict[str, Any] = {"type": "result", "subtype": "success"}
    if model_usage is not None:
        event["modelUsage"] = model_usage
    return event


def _mu(
    inp: int = 1,
    read: int = 2,
    w5: int | None = 3,
    w1: int | None = 4,
    out: int = 5,
    **extra: Any,
) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "inputTokens": inp,
        "cacheReadInputTokens": read,
        "outputTokens": out,
        "costUSD": 0.5,
    }
    if w5 is not None:
        usage["cacheCreationEphemeral5mInputTokens"] = w5
    if w1 is not None:
        usage["cacheCreationEphemeral1hInputTokens"] = w1
    usage.update(extra)
    return {"m1": usage}


def _write(tmp_path: Path, events: list[dict[str, Any]], raw: str | None = None) -> Path:
    path = tmp_path / "log.jsonl"
    path.write_text(raw if raw is not None else "\n".join(json.dumps(e) for e in events) + "\n")
    return path


def _stream() -> list[dict[str, Any]]:
    return [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [_call("t1", "Bash", command="pytest -q"), _call("t2", "Read", file_path="/f")],
            usage=_usage(),
        ),
        _result(("t1", True), ("t2", False)),
        _assistant("b", "2026-11-12T10:02:00.500Z", usage=_usage()),
        _final(_mu(inp=2, read=4, w5=6, w1=8, out=10)),
    ]


def test_noise_between_and_glued_to_event_lines_changes_nothing(tmp_path: Path) -> None:
    events = _stream()
    clean = _extract(_write(tmp_path, events))
    lines = [json.dumps(e) for e in events]
    noisy = "\n".join(
        [
            "npm warn deprecated foo@1: gone",
            "OTLPExporterError: Export failed {not json",
            "npm warn glued " + lines[0],
            lines[1],
            "[otel] exporter error",
            lines[2],
            lines[3],
        ]
    )
    noisy_path = tmp_path / "noisy.jsonl"
    noisy_path.write_text(noisy + "\n")
    got = _extract(noisy_path)
    assert got == clean
    assert clean.gaps[0].gaps_s == (120,)


def test_no_model_usage_is_partial_and_writes_no_usage_rows(tmp_path: Path) -> None:
    events = [*_stream()[:-1], _final(None)]
    facts = _extract(_write(tmp_path, events))
    assert facts.status == "partial"
    assert facts.reason == NO_MODEL_USAGE == "no modelUsage"
    assert facts.usage == ()
    assert facts.requests
    assert facts.activity
    assert facts.gaps


def test_a_missing_log_is_partial_and_empty(tmp_path: Path) -> None:
    facts = _extract(tmp_path / "absent.log")
    assert (facts.status, facts.reason) == ("partial", NO_MODEL_USAGE)
    assert facts == AttemptFacts(status="partial", reason=NO_MODEL_USAGE)


def test_a_repeated_message_id_counts_once_and_the_later_event_wins(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", usage=_usage(out=1)),
        _assistant("a", "2026-11-12T10:00:05.000Z", usage=_usage(out=99)),
        _final(_mu(inp=1, read=2, w5=3, w1=4, out=99)),
    ]
    facts = _extract(_write(tmp_path, events))
    assert facts.gaps[0].messages == 1
    assert len(facts.requests) == 1
    assert facts.requests[0].output == 99
    assert facts.requests[0].at is not None
    assert facts.requests[0].at.second == 0


@pytest.mark.parametrize("name", ["Agent", "Task"])
def test_a_subagent_conversation_carries_its_id_and_type(tmp_path: Path, name: str) -> None:
    events = [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [_call("tu1", name, subagent_type="general-purpose")],
            usage=_usage(),
        ),
        _assistant(
            "b",
            "2026-11-12T10:00:10.000Z",
            [_call("tu2", "Write", file_path="/w"), _call("tu3", "Bash", command="make test")],
            parent="tu1",
            usage=_usage(),
        ),
        _assistant("c", "2026-11-12T10:03:10.000Z", parent="tu1", usage=_usage()),
        _final(_mu(inp=3, read=6, w5=9, w1=12, out=15)),
    ]
    facts = _extract(_write(tmp_path, events))
    classes = ("input_uncached", "cache_read", "cache_write_5m", "cache_write_1h")
    sub = [u for u in facts.usage if u.conversation == "tu1"]
    assert {u.usage_class for u in sub} == set(classes)
    assert {u.subagent_type for u in sub} == {"general-purpose"}
    main = [u for u in facts.usage if u.conversation == "main"]
    assert {u.usage_class for u in main} == set(classes)
    assert {u.subagent_type for u in main} == {None}
    assert {r.conversation for r in facts.requests} == {"main", "tu1"}
    assert {a.conversation for a in facts.activity} == {"main", "tu1"}
    assert {g.conversation for g in facts.gaps} == {"main", "tu1"}
    assert {e.conversation for e in facts.events} == {"tu1"}
    sub_gap = next(g for g in facts.gaps if g.conversation == "tu1")
    assert sub_gap.gaps_s == (180,)


def test_an_unknown_parent_id_has_no_subagent_type(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", parent="ghost", usage=_usage()),
        _final(_mu(inp=1, read=2, w5=3, w1=4, out=5)),
    ]
    facts = _extract(_write(tmp_path, events))
    rows = [u for u in facts.usage if u.conversation == "ghost"]
    assert rows
    assert {u.subagent_type for u in rows} == {None}


def test_a_split_that_differs_falls_back_to_model_usage_for_that_model(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", usage=_usage(read=2)),
        _final(_mu(inp=1, read=7, w5=3, w1=4, out=5)),
    ]
    with capture_logs() as logs:
        facts = _extract(_write(tmp_path, events))
    assert facts.status == "ok"
    harness = {u.usage_class: u for u in facts.usage if u.usage_class != "money"}
    assert harness["cache_read"].tokens == 7
    assert {u.conversation for u in facts.usage} == {None}
    assert {u.subagent_type for u in facts.usage} == {None}
    assert len([u for u in facts.usage if u.usage_class == "cache_read"]) == 1
    assert any(entry["event"] == "claude usage split does not match modelUsage" for entry in logs)


def test_a_log_without_message_usage_writes_model_usage_attempt_wide(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z"),
        _final(_mu(inp=1, read=2, w5=3, w1=4, out=5, thinkingTokens=6)),
    ]
    facts = _extract(_write(tmp_path, events))
    assert facts.status == "ok"
    tokens = {u.usage_class: u.tokens for u in facts.usage if u.usage_class != "money"}
    assert tokens == {
        "input_uncached": 1,
        "cache_read": 2,
        "cache_write_5m": 3,
        "cache_write_1h": 4,
        "output": 5,
        "thinking": 6,
    }
    assert {u.conversation for u in facts.usage} == {None}
    assert facts.requests == ()


def test_only_the_last_result_event_counts(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", usage=_usage()),
        _final(_mu()),
        _final(_mu()),
        _final(_mu()),
    ]
    facts = _extract(_write(tmp_path, events))
    assert _sum_model(facts, "output") == 5
    assert len([u for u in facts.usage if u.usage_class == "money"]) == 1


def _sum_model(facts: AttemptFacts, usage_class: str) -> int:
    return sum(u.tokens or 0 for u in facts.usage if u.usage_class == usage_class)


def test_unsplit_cache_write_is_one_row(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z"),
        _final(_mu(w5=None, w1=None, cacheCreationInputTokens=9)),
    ]
    facts = _extract(_write(tmp_path, events))
    unsplit = [u for u in facts.usage if u.usage_class == "cache_write_unsplit"]
    assert [u.tokens for u in unsplit] == [9]
    assert not [u for u in facts.usage if u.usage_class in ("cache_write_5m", "cache_write_1h")]


def test_absent_or_non_numeric_fields_write_no_row(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z"),
        _final({"m1": {"inputTokens": 1, "outputTokens": "n/a", "costUSD": None}}),
    ]
    facts = _extract(_write(tmp_path, events))
    classes = {u.usage_class for u in facts.usage}
    assert "output" not in classes
    assert "money" not in classes
    assert "thinking" not in classes


def test_a_model_without_model_usage_writes_no_usage_rows(tmp_path: Path) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", usage=_usage(), model="other"),
        _final(_mu()),
    ]
    with capture_logs() as logs:
        facts = _extract(_write(tmp_path, events))
    assert {u.model for u in facts.usage} == {"m1"}
    assert logs


def test_is_error_false_is_not_an_error_and_errors_follow_the_tool(tmp_path: Path) -> None:
    events = [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [_call("t1", "Bash", command="ls"), _call("t2", "Read", file_path="/f")],
        ),
        _result(("t1", False), ("t2", True), ("unknown", True)),
        _final(None),
    ]
    facts = _extract(_write(tmp_path, events))
    errors = {a.tool: a.errors for a in facts.activity}
    assert errors == {"Bash": 0, "Read": 1}


def test_files_and_messages_per_tool(tmp_path: Path) -> None:
    events = [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [
                _call("t1", "Edit", file_path="/a"),
                _call("t2", "Edit", file_path="/a"),
                _call("t3", "NotebookEdit", notebook_path="/n.ipynb"),
                _call("t4", "MultiEdit", file_path="/b"),
            ],
        ),
        _assistant("b", "2026-11-12T10:00:01.000Z", [_call("t5", "Edit", file_path="/c")]),
        _final(None),
    ]
    facts = _extract(_write(tmp_path, events))
    by_tool = {a.tool: a for a in facts.activity}
    assert by_tool["Edit"].calls == 3
    assert by_tool["Edit"].files_edited == 2
    assert by_tool["Edit"].messages == 2
    assert by_tool["NotebookEdit"].files_edited == 1
    assert by_tool["MultiEdit"].files_edited == 1
    assert {e.path for e in facts.events if e.kind == "write"} == {"/a", "/c", "/n.ipynb", "/b"}


def test_a_call_without_a_timestamp_writes_no_event_but_counts(tmp_path: Path) -> None:
    events = [
        _assistant("a", None, [_call("t1", "Write", file_path="/a")]),
        _assistant("b", "not a time", [_call("t2", "Bash", command="pytest")]),
        _assistant("c", "2026-11-12T10:00:00.000Z"),
        _final(None),
    ]
    facts = _extract(_write(tmp_path, events))
    assert facts.events == ()
    assert sum(a.calls for a in facts.activity) == 2
    assert facts.gaps[0].messages == 3
    assert facts.gaps[0].gaps_s == ()
    only_untimed = _extract(_write(tmp_path, [*events[:2], _final(None)]))
    assert only_untimed.gaps == ()


def test_a_test_run_counts_once_however_many_patterns_it_holds(tmp_path: Path) -> None:
    events = [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [_call("t1", "Bash", command="make lint && make test && pytest")],
        ),
        _final(None),
    ]
    facts = _extract(_write(tmp_path, events))
    assert facts.activity[0].test_runs == 1
    assert [e.kind for e in facts.events] == ["test_run"]


@pytest.mark.parametrize(
    ("command", "counts"),
    [
        ("cd x && make test > log", True),
        ("make tests", False),
        ("pytest -q", True),
        ("npm run lint", False),
        ("uv run pytest", True),
        ("./pytest", False),
    ],
)
def test_test_run_matching_is_whole_words(tmp_path: Path, command: str, counts: bool) -> None:
    events = [
        _assistant("a", "2026-11-12T10:00:00.000Z", [_call("t1", "Bash", command=command)]),
        _final(None),
    ]
    facts = _extract(_write(tmp_path, events))
    assert facts.activity[0].test_runs == (1 if counts else 0)


def test_the_default_patterns_equal_the_catalogue_parameter() -> None:
    assert DEFAULT_TEST_RUN_PATTERNS == registry.test_run_patterns(PackageCatalogue())


def test_missing_catalogue_parameter_is_a_programming_error() -> None:
    class Empty:
        def entries(self) -> tuple[()]:
            return ()

    with pytest.raises(KeyError):
        registry.test_run_patterns(Empty())  # type: ignore[arg-type]


def test_the_registry_redacts_a_secret_in_a_test_run_command(
    env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings()
    token = settings.github_token.get_secret_value()
    events = [
        _assistant(
            "a",
            "2026-11-12T10:00:00.000Z",
            [_call("t1", "Bash", command=f"pytest --token {token}")],
        ),
        _final(None),
    ]
    registry = build_log_facts(settings)
    claude = registry["claude"]
    assert isinstance(claude, RedactingLogFacts)
    assert claude.name == "claude"
    facts = claude.extract(_attempt(), str(_write(tmp_path, events)))
    assert [e.command for e in facts.events] == ["pytest --token ***"]
