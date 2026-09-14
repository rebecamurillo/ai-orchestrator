"""`NullTracer` — the off-path behind the `Tracer` port when `tracing_enabled` is False (AD-11, 9-2).

No `langfuse` symbol is imported here.  The module must be importable in an environment
that has no Langfuse credentials at all (SM-3), and `NullTracer.__init__` must never
trigger the SDK's own background export thread.

**Trace-id determinism.**  `run_id.hex` is 32 lowercase hex characters with no hyphens
— exactly what W3C `traceparent` requires for the trace-id field.  Any later call for
the same Run lands the same id without reading it back, which is the same determinism
property AD-11 pins for `LangfuseTracer`.

**Spans.**  `step_span` and `attempt_span` both delegate to `fallback_span_ref(run.id.hex)`
from `spans.py` — schema-valid, locally generated, a fresh random 16-hex span id each
time.  Every downstream consumer (harness env, cost model, UI) sees a well-formed
`traceparent` string and behaves exactly as it would if an unreachable Langfuse had
caused the real adapter to degrade.  Body exceptions propagate unchanged: the context
manager does not swallow them.

**`attempt_observed`.**  Always `False`.  No harness span exists by definition when
tracing is off.  The `TRACE_OBSERVED` structlog event is still emitted with
`path="disabled"` so the Operator's `grep TRACE_OBSERVED` from 7.2's runbook finds an
entry regardless of which adapter is active.

**`trace_url`.**  Always `None`.  The widened port (`str | None`) accommodates this;
the use-case readers that call it (`history.py::_trace_url`, `run_views.py::run_detail`)
already handle `None` as their own no-tracer case.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

import structlog

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.tracer import SpanRef, TraceRef
from orchestrator.infrastructure.tracing.spans import fallback_span_ref

log = structlog.get_logger(__name__)

#: The same event name `LangfuseTracer.attempt_observed` logs — kept identical so the
#: Operator's log search from the 7.2 runbook finds an entry regardless of which adapter
#: is active.  Exported so `test_null_tracer.py` can reference it without hard-coding
#: the string.
TRACE_OBSERVED = "attempt trace observed"

#: The `path=` value logged by this adapter's `attempt_observed` — distinct from the four
#: values the real adapter uses (`parented`, `session`, `user`, `none`), so a grepper can
#: tell "tracing off" from "tracing on but no observation found".
_PATH_DISABLED = "disabled"


class NullTracer:
    """A `Tracer` that does nothing — no Langfuse client, no network I/O.

    Every method satisfies the port contract:
    - `create_run_trace` returns a `TraceRef` with `trace_id = run_id.hex`.
    - `step_span` / `attempt_span` yield a schema-valid `SpanRef`; body exceptions propagate.
    - `attempt_observed` returns `False` and logs `TRACE_OBSERVED` with `path="disabled"`.
    - `trace_url` returns `None`.
    """

    def create_run_trace(
        self,
        run_id: UUID,
        project_slug: str,
        tags: tuple[str, ...],
        *,
        name: str,
    ) -> TraceRef:
        """Returns a `TraceRef` whose `trace_id` is `run_id.hex` — deterministic and W3C-valid."""
        return TraceRef(trace_id=run_id.hex)

    @contextmanager
    def step_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        """Yields a locally-generated `SpanRef`; body exceptions propagate unchanged."""
        yield fallback_span_ref(run.id.hex)

    @contextmanager
    def attempt_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        """Yields a locally-generated `SpanRef`; body exceptions propagate unchanged."""
        yield fallback_span_ref(run.id.hex)

    def attempt_observed(
        self,
        run_id: UUID,
        attempt_id: UUID,
        *,
        harness: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> bool:
        """Always `False`; logs `TRACE_OBSERVED` with `path="disabled"`."""
        log.info(
            TRACE_OBSERVED,
            run_id=str(run_id),
            attempt_id=str(attempt_id),
            harness=harness,
            path=_PATH_DISABLED,
        )
        return False

    def trace_url(self, trace_id: str) -> str | None:
        """Always `None` — no Langfuse instance, no URL to format."""
        return None
