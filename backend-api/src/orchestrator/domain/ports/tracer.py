"""The `Tracer` port (AD-11): opening a Run's trace, and the spans hung under it.

One trace per Run, opened once by `create_run` and never re-opened: `create_run_trace`'s
`trace_id` is deterministic from `run_id` alone (the real adapter's own docstring says how),
so a later call never has to look one up or store a span id anywhere to find it again.
`step_span` wraps one row's execution; `attempt_span` — a child of the currently-open
`step_span`, called only from 5.4 on — is what hands a harness process the `traceparent`
`infrastructure/harness/env.py::env_for` takes (5.1). `attempt_observed` and `trace_url` are
reads: whether an attempt's own span has reported in (5.8), and the Langfuse UI link for a
trace id (the Run detail's `cost.trace_url`, 5.2's own Scope).

`step_span` and `attempt_span` are plain context managers, not a call that opens a span and
a second one that closes it with a status: the span's lifetime *is* the width of the `with`
block, and the SDK already marks a span `ERROR` when an exception escapes it and `DEFAULT`
otherwise — nothing here adds a sixth method to push a result back onto an already-open
span. Nothing in this story's own production code calls `attempt_span` yet; 5.4's executor
does.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun


@dataclass(frozen=True)
class TraceRef:
    """What `create_run_trace` hands back: the trace id every later span for this Run reuses."""

    trace_id: str


@dataclass(frozen=True)
class SpanRef:
    """One open span: its own ids, and the `traceparent` a harness process can be handed.

    `traceparent` is the W3C string `env_for`'s `traceparent` keyword (5.1) takes verbatim —
    this is the one place that format is built.
    """

    trace_id: str
    span_id: str
    traceparent: str


@runtime_checkable
class Tracer(Protocol):
    """One Run's trace: opened once, spanned per row and per attempt, read back by a URL."""

    def create_run_trace(
        self, run_id: UUID, project_slug: str, tags: tuple[str, ...], *, name: str
    ) -> TraceRef:
        """Open the root trace this Run's every later span hangs under (AD-11)."""
        ...

    def step_span(
        self, run: Run, row: StepRun, attempt: Attempt
    ) -> AbstractContextManager[SpanRef]:
        """A span named by the row's path, open for exactly the width of its execution."""
        ...

    def attempt_span(
        self, run: Run, row: StepRun, attempt: Attempt
    ) -> AbstractContextManager[SpanRef]:
        """A child of the currently-open `step_span`, whose `traceparent` a harness gets.

        Auto-parents through the SDK's own ambient span, so no parent id is passed
        explicitly — safe across a durable-engine replay because `step_span` and this call
        both happen inside one Python call, never split across a replay boundary (5.4's own
        concern; see the real adapter's docstring).
        """
        ...

    def attempt_observed(self, run_id: UUID, attempt_id: UUID) -> bool:
        """Whether the harness's own span for this attempt has reported in yet (5.8)."""
        ...

    def trace_url(self, trace_id: str) -> str:
        """The Langfuse UI link for one trace id — a pure string format, never a network
        call (unlike the SDK's own `get_trace_url()`, whose project-id lookup this avoids)."""
        ...
