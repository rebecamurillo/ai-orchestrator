"""The session-level trace evidence a harness that cannot parent still leaves (AD-11, 7.2).

A sibling of `langfuse_tracer.py` rather than a section of it, for the reason
`tests/unit/test_source_limits.py` makes checkable: that module is at 328 of its 400 lines,
and 7.1's `codex/events.py` was split from `codex/adapter.py` on the same rule. Everything
here is one query and the rule for reading its answer.

**What this is evidence of.** `research/tracing.md` §Codex read `codex exec`'s
`traceparent_context_from_env()` out of the CLI's own source and marked it "verify day 1" —
it is undocumented, so whether the spans a Codex attempt exports actually parent under the
attempt span this orchestrator opened is not a fact until a real run says so. If they do, the
primary query in `langfuse_tracer.py` answers and nothing here runs. If they do not, the
attempt is still not invisible: every gateway request a harness makes carries
`langfuse_session_id = ORCH_RUN_ID` and `langfuse_tags = ORCH_LANGFUSE_TAGS` through that
harness's own env-name header mechanism (`scripts/harness/codex.sh`'s `env_http_headers`), so
Langfuse holds at least one trace whose session is the Run and whose tags name the attempt.
That is what `session_level_observed` asks for, and it is the fallback the story brief calls
`TRACEPARENT not honoured · fallback: session-level`.

**Why the traces API and not the observations API.** `api.observations.get_many` does take a
`session_id`, but an observation carries no tags — `langfuse_tags` becomes a *trace* attribute
— so it could not also require the attempt's own tag, and a query by session alone would
accept any attempt of the Run as evidence for this one. `api.trace.list(session_id=…,
tags=[…])` states both halves server-side.

**Why `codex` alone.** AD-10 pins parented spans as `claude`'s rule too, and this system has
no observation of `claude` failing to parent (5.11 never got a model call through). Offering
the same fallback there would quietly change what `enabled` means for a harness this story is
not about. `local` joins by its own rule in 7.3 — generations by user id — not by this one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog

from orchestrator.infrastructure.harness.env import attempt_tag

log = structlog.get_logger(__name__)

#: The harnesses whose `attempt_observed` may fall back to session-level evidence. One
#: today; `tests/unit/test_tracer_session_level.py` pins that it is exactly this one, so
#: adding `local` here in 7.3 is a decision that has to be made rather than one that drifts.
SESSION_LEVEL_HARNESSES: frozenset[str] = frozenset({"codex"})

#: How many of the Run session's tagged traces are looked at. A readiness Run has one
#: attempt and a handful of traces; a long Run's session holds one per gateway request, and
#: the query is already narrowed to this attempt's tag, so this is a ceiling and not a page
#: anything is expected to fill.
SESSION_TRACE_PAGE_LIMIT = 50

#: The three answers `attempt_observed` can give, as the log line's own `path` value — the
#: only place the difference between "honoured" and "fell back" is visible, since the port
#: returns a bool and the readiness line's wording is pinned by `tests/e2e/test_harnesses.py`.
PATH_PARENTED = "parented"
PATH_SESSION = "session"
PATH_NONE = "none"

#: Logged (never raised) when the session-level query itself fails: the same degradation
#: `langfuse_tracer.py`'s primary query already makes, for the same SM-3 reason.
SESSION_QUERY_FAILED = "langfuse session-level observation query failed; answering not-observed"


def session_level_observed(client_ref: Callable[[], Any], run_id: UUID, attempt_id: UUID) -> bool:
    """Whether Langfuse holds an observation for this attempt under the Run's own session.

    True when at least one trace of session `run_id` carries the tag `attempt:{attempt_id}`
    **and** names at least one observation. A trace whose `observations` list comes back
    empty is rejected: a trace row is not a span, and a readiness check that accepted one
    would report a harness observed on the strength of a record it never wrote. The field is
    optional on the API's own model, so absent means "not expanded" rather than "none" and is
    accepted — the trace exists because something was ingested under it, and 7.2's runbook has
    the Operator confirm that in the UI rather than leaving it inferred.

    The client arrives as the caller's own accessor rather than as a built client, so that
    building it is inside this function's guard too: `LangfuseTracer` constructs its SDK
    client lazily, on first use, and a construction that raises here must degrade exactly
    like a query that raises rather than escaping into a readiness evaluation.

    Never raises (SM-3): a failure answers exactly what a not-yet-observed attempt already
    answers.
    """
    try:
        traces = (
            client_ref()
            .api.trace.list(
                session_id=str(run_id),
                tags=[attempt_tag(str(attempt_id))],
                limit=SESSION_TRACE_PAGE_LIMIT,
            )
            .data
            or []
        )
    except Exception:
        log.exception(SESSION_QUERY_FAILED, run_id=str(run_id), attempt_id=str(attempt_id))
        return False
    return any(_holds_an_observation(trace) for trace in traces)


def _holds_an_observation(trace: Any) -> bool:
    """Whether this trace names an observation, treating an unexpanded field as unknown."""
    observations = getattr(trace, "observations", None)
    return observations is None or bool(observations)
