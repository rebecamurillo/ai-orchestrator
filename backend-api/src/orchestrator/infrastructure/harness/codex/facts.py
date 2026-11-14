"""Codex's `exec --json` attempt log, read into facts after the harness has exited (AD-10).

Only the framing `type` and the `turn.completed` usage counts are read.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, UsageClass, UsageFact
from orchestrator.infrastructure.harness import jsonl
from orchestrator.infrastructure.harness.codex import events as codex
from orchestrator.infrastructure.harness.stream_facts import (
    NO_CAPABILITIES,
    split_events,
    status_and_reason,
    usage_row,
)

KNOWN_EVENT_TYPES = frozenset(
    {codex.THREAD_STARTED, "turn.started", "item.completed", codex.TURN_COMPLETED}
)
CACHED_INPUT_TOKENS = "cached_input_tokens"


class CodexLogFacts:
    """The `LogFacts` extractor for harness `codex`."""

    name = "codex"
    version = 1
    capabilities = NO_CAPABILITIES

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        stream, unknown = split_events(
            codex.events(jsonl.read_text(Path(log_path))), KNOWN_EVENT_TYPES
        )
        completed = [
            e
            for e in jsonl.objects_with(stream, codex.EVENT_TYPE, codex.TURN_COMPLETED)
            if isinstance(e.get(codex.USAGE), dict)
        ]
        # `usage` is the session's running total: only the last turn counts.
        usage = _usage(attempt, completed[-1][codex.USAGE]) if completed else ()
        status, reason = status_and_reason(bool(completed), unknown)
        return AttemptFacts(status=status, reason=reason, usage=usage)


def _usage(attempt: Attempt, usage: dict[str, object]) -> tuple[UsageFact, ...]:
    # OpenAI's `input_tokens` includes the cached ones; the catalogue's input is the uncached.
    tokens_in = jsonl.as_int(usage.get(codex.INPUT_TOKENS))
    cached = jsonl.as_int(usage.get(CACHED_INPUT_TOKENS))
    output = jsonl.as_int(usage.get(codex.OUTPUT_TOKENS))
    uncached = None if tokens_in is None else max(tokens_in - (cached or 0), 0)
    rows: tuple[tuple[UsageClass, int | None], ...] = (
        ("input_uncached", uncached),
        ("cache_read", cached),
        ("output", output),
    )
    return tuple(usage_row(attempt, cls, n) for cls, n in rows if n is not None)
