"""In-memory `Tracer` — the one fake for that port (AD-18). Reuse it; do not write another.

`trace_id` is derived from the given `run.id`/`run_id` alone (`f"trace-{id}"`), the same
determinism `AD-11`'s real adapter gets from `Langfuse.create_trace_id(seed=...)`: two calls
naming the same Run always agree, without either one reading the other's answer back.
`span_id` is a per-instance counter, so a test asserting an exact `TRACEPARENT` string does
not have to guess which call produced which id. Every call is recorded, with its arguments,
the same way `fakes/git.py` and `fakes/process.py` record theirs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.tracer import SpanRef, TraceRef

#: The two constant W3C `traceparent` fields this fake always writes: version, then flags.
_TP_VERSION = "00"
_TP_FLAGS = "01"


def trace_id_of(run_id: UUID) -> str:
    """The deterministic id this fake gives Run `run_id` — exported so a test can predict it
    without reaching into a `FakeTracer` instance first."""
    return f"trace-{run_id}"


class FakeTracer:
    """Scripted `attempt_observed` answers, a call log, and deterministic trace/span ids."""

    def __init__(self) -> None:
        self.create_run_trace_calls: list[tuple[UUID, str, tuple[str, ...], str]] = []
        self.step_span_calls: list[tuple[UUID, str, UUID]] = []
        self.attempt_span_calls: list[tuple[UUID, str, UUID]] = []
        #: `(run_id, attempt_id) -> observed`; a pair not in here answers `False`.
        self.observed: dict[tuple[UUID, UUID], bool] = {}
        self._span_n = 0

    def create_run_trace(
        self, run_id: UUID, project_slug: str, tags: tuple[str, ...], *, name: str
    ) -> TraceRef:
        self.create_run_trace_calls.append((run_id, project_slug, tags, name))
        return TraceRef(trace_id=trace_id_of(run_id))

    @contextmanager
    def step_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        self.step_span_calls.append((run.id, row.path, attempt.id))
        yield self._span(run.id)

    @contextmanager
    def attempt_span(self, run: Run, row: StepRun, attempt: Attempt) -> Iterator[SpanRef]:
        self.attempt_span_calls.append((run.id, row.path, attempt.id))
        yield self._span(run.id)

    def attempt_observed(self, run_id: UUID, attempt_id: UUID) -> bool:
        return self.observed.get((run_id, attempt_id), False)

    def trace_url(self, trace_id: str) -> str:
        return f"https://fake-langfuse.test/project/p/traces/{trace_id}"

    def _span(self, run_id: UUID) -> SpanRef:
        self._span_n += 1
        trace_id = trace_id_of(run_id)
        span_id = f"{self._span_n:016x}"
        return SpanRef(
            trace_id=trace_id,
            span_id=span_id,
            traceparent=f"{_TP_VERSION}-{trace_id}-{span_id}-{_TP_FLAGS}",
        )
