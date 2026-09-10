"""Building a `SpanRef` — the W3C `traceparent` a harness process is handed (AD-11).

Moved out of `langfuse_tracer.py` whole, unchanged, when 7.3 added the third
`attempt_observed` rule: that module was at 375 of the 400 lines
`tests/unit/test_source_limits.py` enforces, and `backend-api/AGENTS.md` says a capped module
is split rather than trimmed. This is the split, and it is a real seam rather than an arbitrary
cut — everything here is pure string construction over an SDK span, with no client, no
settings, and no I/O, which is why it needs none of the adapter's own machinery.

The two builders differ in one thing and it is the reason both exist. `_span_ref` reports
what the SDK actually recorded (`span.trace_id`/`span.id`), so a nested `attempt_span` — which
names no trace id of its own — reports the trace it was really attached to. `fallback_span_ref`
is for when opening the real span failed: it is schema-valid and locally generated, so the row
executes exactly as it would against a healthy Langfuse (`langfuse_tracer.py`'s "side channel,
never a hard dependency" section says why nothing downstream depends on the span having reached
Langfuse at all).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from orchestrator.domain.ports.tracer import SpanRef

#: The two constant positions of a W3C `traceparent`: version, then flags. `env_for`'s own
#: `traceparent` keyword (5.1) takes the joined string verbatim.
TP_VERSION = "00"
TP_FLAGS = "01"

#: How many hex characters a W3C span id has — what a locally generated one must match.
SPAN_ID_HEX = 16


def span_ref(span: Any) -> SpanRef:
    """A `SpanRef` off whatever the SDK actually recorded — never a value computed here."""
    return SpanRef(
        trace_id=span.trace_id,
        span_id=span.id,
        traceparent=f"{TP_VERSION}-{span.trace_id}-{span.id}-{TP_FLAGS}",
    )


def fallback_span_ref(trace_id: str) -> SpanRef:
    """A schema-valid `SpanRef` for when opening the real span failed."""
    span_id = uuid4().hex[:SPAN_ID_HEX]
    return SpanRef(
        trace_id=trace_id,
        span_id=span_id,
        traceparent=f"{TP_VERSION}-{trace_id}-{span_id}-{TP_FLAGS}",
    )
