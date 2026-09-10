"""`SpanRef` construction, split out of `langfuse_tracer.py` when 7.3 needed the room.

The move is a **split, not a trim** (`backend-api/AGENTS.md`: a module is ≤ 400 lines, and a
capped one is split): `langfuse_tracer.py` was at 375 of 400 and this story adds a third
`attempt_observed` rule to it. Nothing about the two builders changed, so this module states
what they were already relied on for — `test_langfuse_tracer.py` (frozen) exercises them
through the adapter, and these assertions are about the strings themselves.

What is worth pinning here is the W3C shape, because it is the one thing in this system that
another *process* has to parse: `env_for` puts `traceparent` into a harness's environment
verbatim (5.1), and a malformed one is not an error anybody sees — the harness simply exports
its spans somewhere else, and `attempt_observed` reports "no spans" for a run that traced
perfectly well.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from orchestrator.domain.ports.tracer import SpanRef
from orchestrator.infrastructure.tracing.spans import (
    SPAN_ID_HEX,
    TP_FLAGS,
    TP_VERSION,
    fallback_span_ref,
    span_ref,
)

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"
#: `version-traceid-spanid-flags`, all lowercase hex — the W3C `traceparent` header format.
TRACEPARENT = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


@dataclass(frozen=True)
class _StubSpan:
    """What the SDK hands back: the ids it actually recorded, not ones we computed."""

    trace_id: str
    id: str


def test_the_ref_reports_the_ids_the_sdk_recorded() -> None:
    """A nested `attempt_span` names no trace id of its own, so reading them back off the
    span is what makes it report the trace it was really attached to."""
    ref = span_ref(_StubSpan(trace_id=TRACE_ID, id=SPAN_ID))

    assert isinstance(ref, SpanRef)
    assert (ref.trace_id, ref.span_id) == (TRACE_ID, SPAN_ID)


def test_the_traceparent_is_the_w3c_string_a_harness_can_parse() -> None:
    ref = span_ref(_StubSpan(trace_id=TRACE_ID, id=SPAN_ID))

    assert ref.traceparent == f"{TP_VERSION}-{TRACE_ID}-{SPAN_ID}-{TP_FLAGS}"
    assert TRACEPARENT.match(ref.traceparent)


def test_the_sampled_flag_is_set_so_the_harness_exports_rather_than_drops() -> None:
    assert TP_FLAGS == "01"


def test_the_fallback_is_schema_valid_on_the_trace_it_was_given() -> None:
    """Opening the real span failed; the row still executes, and against something a harness
    can parse — `langfuse_tracer.py`'s "side channel, never a hard dependency" section."""
    ref = fallback_span_ref(TRACE_ID)

    assert ref.trace_id == TRACE_ID
    assert len(ref.span_id) == SPAN_ID_HEX
    assert TRACEPARENT.match(ref.traceparent)


def test_two_fallbacks_are_two_different_spans() -> None:
    """Two rows degrading in the same Run must not look like one span reported twice."""
    assert fallback_span_ref(TRACE_ID).span_id != fallback_span_ref(TRACE_ID).span_id
