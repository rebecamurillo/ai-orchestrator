"""`LangfuseTracer`: the `Tracer` port's real adapter (AD-11), verified live against the
real `langfuse` SDK 4.15.1 — see `research/tracing.md` and this story's own spike.

**Determinism, not storage.** `Langfuse.create_trace_id(seed=str(run_id))` is a
`staticmethod`: it needs no client and does no I/O, and the same seed always answers the
same 32-hex-character id. `create_run_trace`, `step_span`, `attempt_span` and
`attempt_observed` all recompute it from `run_id` rather than reading `Run.trace_id` back,
which is the whole point AD-11 is pinning — a later span finds the Run's trace without this
adapter, or anything else, having to store a span id anywhere.

**The client is lazy.** Built on first use of any method that actually talks to Langfuse —
never by `trace_url`, which is pure string formatting from `Settings` alone, and never by
`__init__`, so a caller that never opens a trace (most requests) never starts the SDK's
background export thread. `infrastructure/dbos/startup.py::walker_deps` builds one instance
for the whole process's walker; `api/providers.py` builds one per request — cheap either
way, because of this. `_client_ref` double-checks under a lock: the walker can run more
than one Run's rows concurrently (`MAX_ACTIVE_RUNS` > 1), and two rows racing to open their
first span must still land on the one client this instance means to hold.

**Why `attempt_span` needs no explicit parent.** Verified live, and the reason `step_span`
and `attempt_span` are *not* the same private helper underneath: passing `trace_context`
at all — even naming the trace the ambient span already belongs to — makes
`start_as_current_observation` open a fresh logical root under it, discarding whatever
span was current. Real nesting only happens when a nested call passes **no** `trace_context`
and lets the SDK read the ambient one from `contextvars`. So `step_span` (nothing is open
yet when `run_row` calls it) passes `trace_context={"trace_id": ...}` to root itself on the
Run's trace, and `attempt_span` (opened from inside an already-open `step_span`, 5.4) passes
none at all, inheriting both the trace id and the parent span from whichever `step_span` is
currently open. `run_row`'s `step_span` call and 5.4's future `attempt_span` call both
happen inside one Python call on one durable step (`walk.attempt_row` → `run_row` →
`execute` → the row's executor) — never split across a replay boundary, since a replay
re-runs the step from the top and re-establishes the ambient context fresh.

**Identity: `session_id`/`user_id`, tags, and per-span attributes.** The brief's own
binding rule pins these on the root observation: `session_id = run_id`, `user_id = run_id`
(what makes Langfuse's Sessions view group every harness call under one Run — the
"Universal floor" `research/tracing.md` names), tags `run:{id}`/`project:{slug}`, name
`run {template}@{v} {branch}`. Verified live: the OTel span API itself has no `tags`/
`session_id` parameter, so these are set through the SDK's own public
`langfuse.propagate_attributes(...)` context manager — not the private, ingestion-only
trace-tag call an earlier draft of this adapter used — wrapped around the root
observation's own creation. Each Step span carries `run_id`/`path`/`kind`/`attempt` in its
metadata; the attempt span carries `attempt_id`/`harness`/`model`/`story_id` — a `None`
value (an `agent` row's `attempt.model` before the harness reports one, or a row outside a
Story frame) is simply omitted from the exported attributes rather than sent as a literal
`"None"` (verified live).

**Why `trace_url` never calls `get_trace_url()`.** Verified live: the SDK's own
`get_trace_url()` makes a blocking API call the first time it runs (`self.api.projects.get()`)
to resolve a project id. `Settings.langfuse_project_id` exists so this adapter can format the
same URL — `{base_url}/project/{project_id}/traces/{trace_id}` — without ever making that
call.

**Why a client-side export timeout.** Verified live against a refused connection: the SDK
catches every exporter failure inside itself and never raises, but `flush()`/the batch
exporter can still block for the client's export timeout on each attempt while an endpoint
is unreachable. `EXPORT_TIMEOUT_SECONDS` is shorter than the SDK's own 10-second default so
an unreachable Langfuse cannot stall a caller for that long — a fixed implementation
constant, not a setting (this story's own deferred).

**Tracing is a side channel, never a hard dependency (SM-3).** A refused connection is the
one failure mode verified live to never raise out of the SDK — but client *construction*,
`create_trace_id`, or `start_as_current_observation` itself raising for some other reason
(a malformed key, a future SDK behaviour change) is not covered by that guarantee. Every
method below therefore catches any exception the SDK itself raises, logs it, and degrades:
`create_run_trace` still returns the deterministic `TraceRef` (cheap to compute regardless,
so `run.trace_id` is still stored correctly for later spans to reuse); `step_span`/
`attempt_span` still `yield` a schema-valid, locally-generated `SpanRef` so the row
executes exactly as it would with a healthy Langfuse; `attempt_observed` answers `False` —
the same thing an unscripted or not-yet-observed pair already means. A row's own exception
(raised by `execute(context)` inside `with tracer.step_span(...):`) is never one of these:
it is re-raised exactly as thrown, once the span this adapter itself opened (if any) has
been closed and flushed.

**`attempt_observed`'s real query.** Not AC-gated (5.8 exercises it for real): it looks
through at most `OBSERVATION_PAGE_LIMIT` of the trace's own observations for the one whose
metadata names `attempt_id`, then reports whether any observation in that same page names
it as `parent_observation_id` — a trace with more observations than the page limit before
the attempt's own span could under-report (recorded as this story's own deferred).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import structlog
from langfuse import Langfuse, propagate_attributes

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.tracer import SpanRef, TraceRef
from orchestrator.infrastructure.settings import Settings

log = structlog.get_logger(__name__)

#: Shorter than the SDK's own 10-second default (this story's own spike, verified live
#: against a refused connection) — see the module docstring.
EXPORT_TIMEOUT_SECONDS = 2

#: How many of a trace's observations `attempt_observed` looks through before giving up.
OBSERVATION_PAGE_LIMIT = 100

#: The field groups `get_many` needs so `metadata` (where `attempt_id` lives) comes back —
#: the default response omits it (verified live).
OBSERVATION_FIELDS = "core,basic,metadata"

#: The two constant positions of a W3C `traceparent`: version, then flags. `env_for`'s own
#: `traceparent` keyword (5.1) takes the joined string verbatim.
_TP_VERSION = "00"
_TP_FLAGS = "01"

#: The metadata key `attempt_span` writes and `attempt_observed` matches on.
_ATTEMPT_ID_KEY = "attempt_id"

#: Logged (never raised) whenever the SDK itself fails inside one of this adapter's calls —
#: see the module docstring's own "side channel, never a hard dependency" section.
TRACER_CALL_FAILED = "langfuse tracer call failed; degrading gracefully (SM-3)"


class LangfuseTracer:
    """`Tracer`, built once per process (the walker) or once per request (`api/providers.py`)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Langfuse | None = None
        self._client_lock = threading.Lock()

    def create_run_trace(
        self, run_id: UUID, project_slug: str, tags: tuple[str, ...], *, name: str
    ) -> TraceRef:
        """Open (and immediately close) the root observation a Run's trace is named by.

        `session_id`/`user_id` (both `run_id`) and the tags — `run:{run_id}`,
        `project:{project_slug}`, plus whatever the caller passed (`()` throughout this
        epic — no extra tags exist at Run-creation time) — are set through
        `propagate_attributes`, the SDK's public mechanism for trace-level identity; the
        module docstring says why not the private, ingestion-only trace-tag call an
        earlier draft of this adapter used instead.
        """
        trace_id = _trace_id(run_id)
        all_tags = [f"run:{run_id}", f"project:{project_slug}", *tags]
        metadata = {"run_id": str(run_id), "project_slug": project_slug}
        try:
            with (
                propagate_attributes(
                    session_id=str(run_id), user_id=str(run_id), tags=all_tags, trace_name=name
                ),
                self._client_ref().start_as_current_observation(
                    trace_context={"trace_id": trace_id},
                    name=name,
                    as_type="span",
                    metadata=metadata,
                ),
            ):
                pass
            # flush on shutdown and after each step span — the brief's own binding rule; a
            # short-lived root observation must not be lost to the batch exporter's own
            # timer if the process is killed shortly after `create_run` returns.
            self._client_ref().flush()
        except Exception:
            log.exception(TRACER_CALL_FAILED, method="create_run_trace", run_id=str(run_id))
        return TraceRef(trace_id=trace_id)

    @contextmanager
    def step_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        """Rooted explicitly on the Run's own trace id — see the module docstring for why
        this, and not `attempt_span`, is the one that passes `trace_context`. Carries
        `run_id`/`path`/`kind`/`attempt` in its metadata (the brief's own binding rule).

        Flushed in a `finally`, whether or not the row's own execution raised: short-lived
        steps must not lose a span to the batch exporter's own timer on a kill (the brief's
        own binding rule). A failure opening the real span is caught and logged, never
        raised — the row still executes, against a locally-generated fallback `SpanRef` —
        but the row's *own* exception is always re-raised untouched (the module docstring's
        "side channel, never a hard dependency" section says why the two are not the same).
        """
        trace_id = _trace_id(run.id)
        metadata = {"run_id": str(run.id), "path": row.path, "kind": row.kind, "attempt": attempt.n}
        entered = False
        try:
            with self._client_ref().start_as_current_observation(
                trace_context={"trace_id": trace_id},
                name=row.path,
                as_type="span",
                metadata=metadata,
            ) as span:
                entered = True
                yield _span_ref(span)
        except Exception:
            if entered:
                raise
            log.exception(TRACER_CALL_FAILED, method="step_span", run_id=str(run.id))
            yield _fallback_span_ref(trace_id)
        finally:
            self._safe_flush()

    @contextmanager
    def attempt_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        """No `trace_context`: auto-parents under whichever `step_span` is currently open
        (the module docstring says why that is the whole point). Carries `attempt_id`/
        `harness`/`model`/`story_id` in its metadata (the brief's own binding rule) — a
        `None` value (no model reported yet, no Story frame) is simply omitted.

        Flushed and degrades the same way `step_span` is, and for the same reasons.
        """
        trace_id = _trace_id(run.id)
        metadata = {
            _ATTEMPT_ID_KEY: str(attempt.id),
            "harness": attempt.harness,
            "model": attempt.model,
            "story_id": row.story_id,
        }
        entered = False
        try:
            with self._client_ref().start_as_current_observation(
                name=f"{row.path} attempt {attempt.n}",
                as_type="span",
                metadata=metadata,
            ) as span:
                entered = True
                yield _span_ref(span)
        except Exception:
            if entered:
                raise
            log.exception(TRACER_CALL_FAILED, method="attempt_span", run_id=str(run.id))
            yield _fallback_span_ref(trace_id)
        finally:
            self._safe_flush()

    def attempt_observed(self, run_id: UUID, attempt_id: UUID) -> bool:
        trace_id = _trace_id(run_id)
        try:
            observations = (
                self._client_ref()
                .api.observations.get_many(
                    trace_id=trace_id,
                    limit=OBSERVATION_PAGE_LIMIT,
                    fields=OBSERVATION_FIELDS,
                )
                .data
            )
        except Exception:
            # a query failure answers exactly what an unscripted or not-yet-observed pair
            # already means: not confirmed observed — never raised (SM-3).
            log.exception(
                TRACER_CALL_FAILED,
                method="attempt_observed",
                run_id=str(run_id),
                attempt_id=str(attempt_id),
            )
            return False
        mine = next(
            (
                observation
                for observation in observations
                if _attempt_id_of(observation) == str(attempt_id)
            ),
            None,
        )
        if mine is None:
            return False
        return any(observation.parent_observation_id == mine.id for observation in observations)

    def trace_url(self, trace_id: str) -> str:
        base = self._settings.langfuse_base_url.rstrip("/")
        return f"{base}/project/{self._settings.langfuse_project_id}/traces/{trace_id}"

    def _safe_flush(self) -> None:
        try:
            self._client_ref().flush()
        except Exception:
            log.exception(TRACER_CALL_FAILED, method="flush")

    def _client_ref(self) -> Langfuse:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = Langfuse(
                        public_key=self._settings.langfuse_public_key,
                        secret_key=self._settings.langfuse_secret_key.get_secret_value(),
                        base_url=self._settings.langfuse_base_url,
                        environment=self._settings.langfuse_environment,
                        timeout=EXPORT_TIMEOUT_SECONDS,
                    )
        return self._client


def _trace_id(run_id: UUID) -> str:
    return Langfuse.create_trace_id(seed=str(run_id))


def _span_ref(span: Any) -> SpanRef:
    """A `SpanRef` off whatever the SDK actually recorded — `span.trace_id`/`span.id`,
    not a value this adapter computed itself, so a nested `attempt_span` (which never names
    a trace id of its own) reports the trace it was really attached to."""
    return SpanRef(
        trace_id=span.trace_id,
        span_id=span.id,
        traceparent=f"{_TP_VERSION}-{span.trace_id}-{span.id}-{_TP_FLAGS}",
    )


def _fallback_span_ref(trace_id: str) -> SpanRef:
    """A schema-valid `SpanRef` for when opening the real span failed — the module
    docstring's "side channel, never a hard dependency" section says why the row still
    executes normally either way, since nothing downstream depends on the span having
    actually reached Langfuse."""
    span_id = uuid4().hex[:16]
    return SpanRef(
        trace_id=trace_id,
        span_id=span_id,
        traceparent=f"{_TP_VERSION}-{trace_id}-{span_id}-{_TP_FLAGS}",
    )


def _attempt_id_of(observation: Any) -> str | None:
    """The `attempt_id` an observation's own metadata names, or `None` for any shape that
    is not the `{"attempt_id": "..."}` dict `attempt_span` itself writes."""
    metadata = observation.metadata
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(_ATTEMPT_ID_KEY)
    return value if isinstance(value, str) else None
