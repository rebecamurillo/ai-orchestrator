"""The Claude extractor's `read` events and the `files_read` capability (story 6, AC1-AC3)."""

# ruff: noqa: PLR2004

from __future__ import annotations

from pathlib import Path

from tests.unit.infrastructure.harness.test_claude_facts import (
    FIXTURE,
    _assistant,
    _call,
    _extract,
    _final,
    _write,
)

from orchestrator.domain.ports.log_facts import LogFactsCapabilities
from orchestrator.infrastructure.harness.claude.facts import ClaudeLogFacts
from orchestrator.infrastructure.harness.facts import build_log_facts
from orchestrator.infrastructure.settings import Settings

FIXTURE_READ = (
    "~/.claude/projects/<session>/01a1cf2a-b641-74a7-a23a-f93e8d55d22e/tool-results/bwnrg7ipn.txt"
)
T1 = "2026-11-12T09:00:00.000Z"
T2 = "2026-11-12T09:00:01.000Z"


def _reads(tmp_path: Path, events: list[dict]) -> list[str | None]:  # type: ignore[type-arg]
    facts = _extract(_write(tmp_path, [*events, _final(None)]))
    return [e.path for e in facts.events if e.kind == "read"]


def test_the_fixture_holds_one_read_event_and_unchanged_writes_and_test_runs() -> None:
    facts = _extract(FIXTURE)

    assert ClaudeLogFacts.version == 2
    assert [e.path for e in facts.events if e.kind == "read"] == [FIXTURE_READ]
    assert len([e for e in facts.events if e.kind in ("write", "test_run")]) == 3
    assert sum(a.files_read for a in facts.activity) == 1
    runs = [e for e in facts.events if e.kind == "test_run"]
    assert runs[0].at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] == "2026-11-12T09:51:37.323"
    assert "make test" in (runs[0].command or "")


def test_one_read_event_per_distinct_path_in_first_seen_order(tmp_path: Path) -> None:
    stream = [
        _assistant("m1", T1, [_call("t1", "Read", file_path="a.py")]),
        _assistant("m2", T2, [_call("t2", "Read", file_path="a.py")]),
        _assistant("m3", T2, [_call("t3", "Read", file_path="b.py")]),
    ]

    assert _reads(tmp_path, stream) == ["a.py", "b.py"]


def test_untimed_unparseable_and_non_string_reads_add_no_event(tmp_path: Path) -> None:
    stream = [
        _assistant("m1", None, [_call("t1", "Read", file_path="a.py")]),
        _assistant("m2", "not-a-time", [_call("t2", "Read", file_path="b.py")]),
        _assistant("m3", T1, [_call("t3", "Read", file_path=3)]),
        _assistant("m4", T2, [_call("t4", "Read", file_path="a.py")]),
    ]

    assert _reads(tmp_path, stream) == ["a.py"]


def test_the_same_path_in_two_conversations_adds_one_event(tmp_path: Path) -> None:
    stream = [
        _assistant("m1", T1, [_call("t1", "Read", file_path="a.py")]),
        _assistant("m2", T2, [_call("t2", "Read", file_path="a.py")], parent="sub1"),
    ]

    assert _reads(tmp_path, stream) == ["a.py"]


def test_only_claude_declares_files_read(env: dict[str, str]) -> None:
    registry = build_log_facts(Settings())

    assert registry["claude"].capabilities.files_read is True
    for name in ("codex", "opencode", "local", "fake"):
        assert registry[name].capabilities.files_read is False
    assert LogFactsCapabilities(False, False, False, False).files_read is False
