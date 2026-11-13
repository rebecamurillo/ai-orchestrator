"""OpenCode's `run --format json` attempt log, read into facts after the harness has exited (AD-10).

Only the framing `type` and the `message.completed` token counts are read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, UsageClass
from orchestrator.infrastructure.harness import jsonl
from orchestrator.infrastructure.harness.opencode import events as opencode
from orchestrator.infrastructure.harness.stream_facts import (
    NO_CAPABILITIES,
    split_events,
    status_and_reason,
    usage_row,
)

KNOWN_EVENT_TYPES = frozenset(
    {"session.updated", "message.updated", "message.completed", "tool.completed"}
)
MESSAGE_COMPLETED = "message.completed"
CACHE = "cache"


def _classes(tokens: dict[str, Any]) -> dict[UsageClass, int | None]:
    cache = tokens.get(CACHE)
    cache = cache if isinstance(cache, dict) else {}
    return {
        "input_uncached": jsonl.as_int(tokens.get(opencode.INPUT_TOKENS)),
        "output": jsonl.as_int(tokens.get(opencode.OUTPUT_TOKENS)),
        "cache_read": jsonl.as_int(cache.get("read")),
        "cache_write_unsplit": jsonl.as_int(cache.get("write")),
    }


class OpenCodeLogFacts:
    """The `LogFacts` extractor for harnesses `opencode` and `local`."""

    name = "opencode"
    version = 1
    capabilities = NO_CAPABILITIES

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        stream, unknown = split_events(
            opencode.events(jsonl.read_text(Path(log_path))), KNOWN_EVENT_TYPES
        )
        reported = [
            e[opencode.TOKENS]
            for e in jsonl.objects_with(stream, "type", MESSAGE_COMPLETED)
            if isinstance(e.get(opencode.TOKENS), dict)
        ]
        # Each message reports its own tokens, so the attempt's are their sum per class.
        totals: dict[UsageClass, int] = {}
        for tokens in reported:
            for usage_class, n in _classes(tokens).items():
                if n is not None:
                    totals[usage_class] = totals.get(usage_class, 0) + n
        usage = tuple(usage_row(attempt, c, n) for c, n in totals.items())
        status, reason = status_and_reason(bool(reported), unknown)
        return AttemptFacts(status=status, reason=reason, usage=usage)
