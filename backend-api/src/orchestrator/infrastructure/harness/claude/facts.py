"""Claude's `stream-json` attempt log, read into facts after the harness has exited (AD-10).

Only envelope and tool-call fields are read: message ids, models, usage, timestamps, tool names,
tool inputs named below and `is_error`. No text, thinking or tool-result content is read, and
nothing here reaches a status, gate, route, retry, park or prompt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import structlog

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import (
    ActivityFact,
    AttemptFacts,
    EventFact,
    GapFact,
    RequestFact,
    UsageClass,
    UsageFact,
)
from orchestrator.domain.ports.log_facts import LogFactsCapabilities
from orchestrator.infrastructure.harness import jsonl

log = structlog.get_logger(__name__)

NO_MODEL_USAGE = "no modelUsage"
MAIN = "main"
GAP_MIN_S = 60
SUBAGENT_CALLS = ("Agent", "Task")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
DEFAULT_TEST_RUN_PATTERNS = (
    "pnpm test",
    "npm test",
    "yarn test",
    "pytest",
    "vitest",
    "jest",
    "playwright test",
    "make test",
    "go test",
    "cargo test",
)
#: `UsageClass` of each input class, with its `message.usage` reader and its `modelUsage` key.
INPUT_CLASSES: tuple[tuple[UsageClass, str], ...] = (
    ("input_uncached", "inputTokens"),
    ("cache_read", "cacheReadInputTokens"),
    ("cache_write_5m", "cacheCreationEphemeral5mInputTokens"),
    ("cache_write_1h", "cacheCreationEphemeral1hInputTokens"),
)


@dataclass
class _Message:
    conversation: str
    at: datetime | None
    model: str | None = None
    usage: Mapping[str, Any] | None = None


@dataclass
class _Tool:
    calls: int = 0
    errors: int = 0
    read: set[str] = field(default_factory=set)
    edited: set[str] = field(default_factory=set)
    test_runs: int = 0
    messages: set[str] = field(default_factory=set)


@dataclass
class _Reading:
    messages: dict[str, _Message] = field(default_factory=dict)
    tools: dict[tuple[str, str], _Tool] = field(default_factory=dict)
    call_owner: dict[str, tuple[str, str]] = field(default_factory=dict)
    events: list[EventFact] = field(default_factory=list)


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _blocks(event: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    content = _dict(event.get("message")).get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind]


def _count(value: object) -> int:
    return jsonl.as_int(value) or 0


def _request_classes(usage: Mapping[str, Any]) -> dict[str, int]:
    split = _dict(usage.get("cache_creation"))
    return {
        "input_uncached": _count(usage.get("input_tokens")),
        "cache_read": _count(usage.get("cache_read_input_tokens")),
        "cache_write_5m": _count(split.get("ephemeral_5m_input_tokens")),
        "cache_write_1h": _count(split.get("ephemeral_1h_input_tokens")),
    }


class ClaudeLogFacts:
    """The `LogFacts` extractor for harness `claude`."""

    name = "claude"
    version = 1
    capabilities = LogFactsCapabilities(
        per_request_usage=True, activity=True, events=True, harness_money_per_model=True
    )

    def __init__(self, test_run_patterns: tuple[str, ...] = DEFAULT_TEST_RUN_PATTERNS) -> None:
        self._test_run = [
            re.compile(r"(?<![\w./-])" + r"\s+".join(map(re.escape, p.split())) + r"(?![\w-])")
            for p in test_run_patterns
        ]

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        events = jsonl.json_objects(jsonl.read_text(Path(log_path)))
        subagents = self._subagent_types(events)
        read = _Reading()
        messages, tools = read.messages, read.tools
        for event in events:
            conversation = str(event.get("parent_tool_use_id") or MAIN)
            if event.get("type") == "assistant":
                self._assistant(event, conversation, read)
        for event in events:
            if event.get("type") == "user":
                for block in _blocks(event, "tool_result"):
                    owner = read.call_owner.get(str(block.get("tool_use_id")))
                    if block.get("is_error") is True and owner is not None:
                        tools[owner].errors += 1
        results = jsonl.objects_with(events, "type", "result")
        model_usage = _dict(results[-1].get("modelUsage")) if results else {}
        usage = self._usage(model_usage, messages, subagents) if model_usage else ()
        return AttemptFacts(
            status="ok" if model_usage else "partial",
            reason=None if model_usage else NO_MODEL_USAGE,
            usage=usage,
            requests=self._requests(messages),
            activity=tuple(
                ActivityFact(
                    conversation=conv,
                    tool=tool,
                    calls=t.calls,
                    errors=t.errors,
                    files_read=len(t.read),
                    files_edited=len(t.edited),
                    test_runs=t.test_runs,
                    messages=len(t.messages),
                )
                for (conv, tool), t in tools.items()
            ),
            gaps=self._gaps(messages),
            events=tuple(read.events),
        )

    @staticmethod
    def _subagent_types(events: list[dict[str, Any]]) -> dict[str, str]:
        found: dict[str, str] = {}
        for event in events:
            for block in _blocks(event, "tool_use"):
                kind = _dict(block.get("input")).get("subagent_type")
                if block.get("name") in SUBAGENT_CALLS and isinstance(kind, str):
                    found[str(block.get("id"))] = kind
        return found

    def _is_test_run(self, command: object) -> bool:
        return isinstance(command, str) and any(p.search(command) for p in self._test_run)

    def _assistant(
        self,
        event: dict[str, Any],
        conversation: str,
        read: _Reading,
    ) -> None:
        message = _dict(event.get("message"))
        mid = str(message.get("id"))
        at = _time(event.get("timestamp"))
        record = read.messages.setdefault(mid, _Message(conversation, at))
        if isinstance(message.get("model"), str):
            record.model = message["model"]
        if isinstance(message.get("usage"), dict):
            record.usage = message["usage"]
        for block in _blocks(event, "tool_use"):
            tool = str(block.get("name"))
            tool_input = _dict(block.get("input"))
            stats = read.tools.setdefault((conversation, tool), _Tool())
            stats.calls += 1
            stats.messages.add(mid)
            read.call_owner[str(block.get("id"))] = (conversation, tool)
            path = tool_input.get("file_path")
            if tool == "NotebookEdit":
                path = path or tool_input.get("notebook_path")
            if tool == "Read" and isinstance(path, str):
                stats.read.add(path)
            if tool in EDIT_TOOLS and isinstance(path, str):
                stats.edited.add(path)
                if at is not None:
                    read.events.append(
                        EventFact(at=at, conversation=conversation, kind="write", path=path)
                    )
            command = tool_input.get("command")
            if tool == "Bash" and self._is_test_run(command):
                stats.test_runs += 1
                if at is not None:
                    read.events.append(
                        EventFact(
                            at=at, conversation=conversation, kind="test_run", command=str(command)
                        )
                    )

    @staticmethod
    def _requests(messages: dict[str, _Message]) -> tuple[RequestFact, ...]:
        rows = []
        for mid, m in messages.items():
            if m.usage is None:
                continue
            classes = _request_classes(m.usage)
            rows.append(
                RequestFact(
                    message_id=mid,
                    model=m.model or "unknown",
                    conversation=m.conversation,
                    at=m.at,
                    output=_count(m.usage.get("output_tokens")),
                    **classes,
                )
            )
        return tuple(rows)

    @staticmethod
    def _gaps(messages: dict[str, _Message]) -> tuple[GapFact, ...]:
        by_conversation: dict[str, list[datetime | None]] = {}
        for m in messages.values():
            by_conversation.setdefault(m.conversation, []).append(m.at)
        gaps = []
        for conversation, stamps in by_conversation.items():
            times = [t for t in stamps if t is not None]
            if not times:
                continue
            seconds = [(b - a).total_seconds() for a, b in pairwise(times)]
            gaps.append(
                GapFact(
                    conversation=conversation,
                    messages=len(stamps),
                    first_at=times[0],
                    last_at=times[-1],
                    gaps_s=tuple(int(s) for s in seconds if s >= GAP_MIN_S),
                )
            )
        return tuple(gaps)

    def _usage(
        self,
        model_usage: dict[str, Any],
        messages: dict[str, _Message],
        subagents: dict[str, str],
    ) -> tuple[UsageFact, ...]:
        rows: list[UsageFact] = []
        for model in {m.model for m in messages.values() if m.usage is not None} - set(model_usage):
            log.warning(
                "claude usage split does not match modelUsage", model=model, usage_class="all"
            )
        for model, raw in model_usage.items():
            figures = _dict(raw)
            for usage_class, key in (("output", "outputTokens"), ("thinking", "thinkingTokens")):
                tokens = jsonl.as_int(figures.get(key))
                if tokens is not None:
                    rows.append(
                        UsageFact(
                            source="harness", model=model, usage_class=usage_class, tokens=tokens
                        )
                    )  # type: ignore[arg-type]
            cost = jsonl.as_decimal(figures.get("costUSD"))
            if cost is not None:
                rows.append(UsageFact(source="harness", model=model, usage_class="money", usd=cost))
            rows.extend(self._input_rows(model, figures, messages, subagents))
        return tuple(rows)

    @staticmethod
    def _input_rows(
        model: str,
        figures: dict[str, Any],
        messages: dict[str, _Message],
        subagents: dict[str, str],
    ) -> list[UsageFact]:
        split: dict[str, dict[str, int]] = {}
        for m in messages.values():
            if m.usage is not None and m.model == model:
                per_class = split.setdefault(m.conversation, dict.fromkeys(dict(INPUT_CLASSES), 0))
                for name, value in _request_classes(m.usage).items():
                    per_class[name] += value
        reported = {name: _count(figures.get(key)) for name, key in INPUT_CLASSES}
        has_split = any(
            jsonl.as_int(figures.get(k)) is not None
            for k in ("cacheCreationEphemeral5mInputTokens", "cacheCreationEphemeral1hInputTokens")
        )
        summed = {n: sum(c[n] for c in split.values()) for n in reported}
        mismatched = [n for n in reported if summed[n] != reported[n]]
        for name in mismatched:
            log.warning(
                "claude usage split does not match modelUsage",
                model=model,
                usage_class=name,
                split=summed[name],
                model_usage=reported[name],
            )
        if split and has_split and not mismatched:
            return [
                UsageFact(
                    source="harness",
                    model=model,
                    conversation=conversation,
                    subagent_type=subagents.get(conversation),
                    usage_class=name,  # type: ignore[arg-type]
                    tokens=value,
                )
                for conversation, per_class in split.items()
                for name, value in per_class.items()
            ]
        if not mismatched:
            log.warning(
                "claude usage split does not match modelUsage", model=model, usage_class="all"
            )
        rows = [
            UsageFact(source="harness", model=model, usage_class=name, tokens=value)  # type: ignore[arg-type]
            for name, key in INPUT_CLASSES
            if (value := jsonl.as_int(figures.get(key))) is not None
        ]
        unsplit = jsonl.as_int(figures.get("cacheCreationInputTokens"))
        if not has_split and unsplit is not None:
            rows.append(
                UsageFact(
                    source="harness", model=model, usage_class="cache_write_unsplit", tokens=unsplit
                )
            )
        return rows
