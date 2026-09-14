"""`NullTracer` and `build_tracer` factory — the off-path behind the Tracer port (AD-11, 9-2).

All tests run without a real Langfuse endpoint.  The three technique families mirror
`test_langfuse_tracer.py`:

- Factory tests use the `env` fixture (`.env.example` values) and optionally override
  `LANGFUSE_BASE_URL` to `""` to force `tracing_enabled=False`.
- `NullTracer` unit tests build the object directly — no settings needed.
- The "Langfuse never constructed" test patches `langfuse.Langfuse` to raise if called,
  then exercises every port method through a `NullTracer` and asserts nothing raised.
- Structlog output is captured via `structlog.testing.capture_logs`, the same pattern
  `test_tracer_session_level.py` and `test_tracer_user_level.py` use.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.tracer import SpanRef, TraceRef, Tracer
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing import LangfuseTracer, NullTracer, build_tracer
from orchestrator.infrastructure.tracing.null import TRACE_OBSERVED

# ── fixed ids used across multiple tests ─────────────────────────────────────────────────
RUN_ID = UUID("00000000-0000-0000-0000-000000000011")
OTHER_RUN_ID = UUID("00000000-0000-0000-0000-000000000022")
STEP_RUN_ID = UUID("00000000-0000-0000-0000-000000000033")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-000000000044")

#: W3C `traceparent` pattern — version 00, 32-hex trace, 16-hex span, flags 01.
_TRACEPARENT_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$")


# ── domain-object factories (mirrors test_langfuse_tracer.py's own, no sharing) ─────────

def _run(run_id: UUID = RUN_ID, *, trace_id: str | None = None) -> Run:
    return Run(
        id=run_id,
        project_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        repository_id=UUID("00000000-0000-0000-0000-0000000000b2"),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        trace_id=trace_id,
    )


def _row() -> StepRun:
    return StepRun(
        id=STEP_RUN_ID,
        run_id=RUN_ID,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
    )


def _attempt() -> Attempt:
    return Attempt(id=ATTEMPT_ID, run_id=RUN_ID, step_run_id=STEP_RUN_ID, n=1, status="running")


# ── build_tracer factory ──────────────────────────────────────────────────────────────────

def test_build_tracer_tracing_off_returns_null_tracer(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blank `LANGFUSE_BASE_URL` ⇒ `tracing_enabled` is False ⇒ `NullTracer`."""
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    tracer = build_tracer(Settings())
    assert isinstance(tracer, NullTracer)
    assert not isinstance(tracer, LangfuseTracer)
    assert isinstance(tracer, Tracer)


def test_build_tracer_tracing_on_returns_langfuse_tracer(env: dict[str, str]) -> None:
    """`env` fixture sets `.env.example` values where `LANGFUSE_BASE_URL` is non-blank."""
    tracer = build_tracer(Settings())
    assert isinstance(tracer, LangfuseTracer)


# ── NullTracer: Langfuse never constructed ────────────────────────────────────────────────

def test_null_tracer_never_constructs_langfuse_client(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patch `langfuse.Langfuse` to raise, then call every port method — nothing raises."""
    import langfuse as _langfuse_module

    def _forbidden(*_args: object, **_kw: object) -> None:
        raise AssertionError("langfuse.Langfuse was constructed by NullTracer")

    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    monkeypatch.setattr(_langfuse_module, "Langfuse", _forbidden)

    tracer = NullTracer()  # built directly — not via build_tracer, to isolate the concern
    run = _run()
    row = _row()
    attempt = _attempt()

    # all five port methods must complete without raising
    ref = tracer.create_run_trace(run.id, "proj", (), name="test")
    assert isinstance(ref, TraceRef)

    with tracer.step_span(run, row, attempt) as span:
        assert isinstance(span, SpanRef)

    with tracer.attempt_span(run, row, attempt) as span:
        assert isinstance(span, SpanRef)

    assert tracer.attempt_observed(run.id, attempt.id) is False
    assert tracer.trace_url("any-id") is None


# ── create_run_trace ──────────────────────────────────────────────────────────────────────

def test_null_tracer_create_run_trace_returns_trace_ref() -> None:
    tracer = NullTracer()
    ref = tracer.create_run_trace(RUN_ID, "my-project", (), name="run epic@1 main")
    assert isinstance(ref, TraceRef)


def test_null_tracer_create_run_trace_trace_id_is_run_id_hex() -> None:
    tracer = NullTracer()
    ref = tracer.create_run_trace(RUN_ID, "proj", (), name="test")
    assert ref.trace_id == RUN_ID.hex


def test_null_tracer_create_run_trace_same_run_id_always_same_trace_id() -> None:
    """Determinism: two calls for the same run id answer identical trace ids."""
    tracer = NullTracer()
    ref1 = tracer.create_run_trace(RUN_ID, "proj-a", ("tag1",), name="run A")
    ref2 = tracer.create_run_trace(RUN_ID, "proj-b", (), name="run B")
    assert ref1.trace_id == ref2.trace_id == RUN_ID.hex


def test_null_tracer_create_run_trace_different_run_ids_give_different_trace_ids() -> None:
    tracer = NullTracer()
    ref1 = tracer.create_run_trace(RUN_ID, "proj", (), name="r1")
    ref2 = tracer.create_run_trace(OTHER_RUN_ID, "proj", (), name="r2")
    assert ref1.trace_id != ref2.trace_id
    assert ref1.trace_id == RUN_ID.hex
    assert ref2.trace_id == OTHER_RUN_ID.hex


# ── step_span ────────────────────────────────────────────────────────────────────────────

def test_null_tracer_step_span_yields_span_ref() -> None:
    tracer = NullTracer()
    with tracer.step_span(_run(), _row(), _attempt()) as span:
        assert isinstance(span, SpanRef)


def test_null_tracer_step_span_trace_id_matches_run_id_hex() -> None:
    tracer = NullTracer()
    run = _run()
    with tracer.step_span(run, _row(), _attempt()) as span:
        assert span.trace_id == run.id.hex


def test_null_tracer_step_span_traceparent_is_w3c_valid() -> None:
    tracer = NullTracer()
    with tracer.step_span(_run(), _row(), _attempt()) as span:
        assert _TRACEPARENT_RE.match(span.traceparent), span.traceparent


def test_null_tracer_step_span_traceparent_embeds_run_id() -> None:
    tracer = NullTracer()
    run = _run()
    with tracer.step_span(run, _row(), _attempt()) as span:
        # traceparent is "00-<trace_id>-<span_id>-01"
        parts = span.traceparent.split("-")
        assert parts[1] == run.id.hex


def test_null_tracer_step_span_propagates_body_exception() -> None:
    class _Boom(Exception):
        pass

    tracer = NullTracer()
    with pytest.raises(_Boom):
        with tracer.step_span(_run(), _row(), _attempt()):
            raise _Boom("from body")


def test_null_tracer_step_span_completes_normally_on_no_exception() -> None:
    tracer = NullTracer()
    reached = False
    with tracer.step_span(_run(), _row(), _attempt()):
        reached = True
    assert reached


# ── attempt_span ─────────────────────────────────────────────────────────────────────────

def test_null_tracer_attempt_span_yields_span_ref() -> None:
    tracer = NullTracer()
    with tracer.attempt_span(_run(), _row(), _attempt()) as span:
        assert isinstance(span, SpanRef)


def test_null_tracer_attempt_span_trace_id_matches_run_id_hex() -> None:
    tracer = NullTracer()
    run = _run()
    with tracer.attempt_span(run, _row(), _attempt()) as span:
        assert span.trace_id == run.id.hex


def test_null_tracer_attempt_span_traceparent_is_w3c_valid() -> None:
    tracer = NullTracer()
    with tracer.attempt_span(_run(), _row(), _attempt()) as span:
        assert _TRACEPARENT_RE.match(span.traceparent), span.traceparent


def test_null_tracer_attempt_span_nested_inside_step_span() -> None:
    """Nesting works: the outer step_span doesn't interfere with the inner attempt_span."""
    tracer = NullTracer()
    run = _run()
    with tracer.step_span(run, _row(), _attempt()) as step:
        with tracer.attempt_span(run, _row(), _attempt()) as attempt:
            assert step.trace_id == run.id.hex
            assert attempt.trace_id == run.id.hex


def test_null_tracer_attempt_span_propagates_body_exception() -> None:
    class _Boom(Exception):
        pass

    tracer = NullTracer()
    with pytest.raises(_Boom):
        with tracer.attempt_span(_run(), _row(), _attempt()):
            raise _Boom("from body")


# ── attempt_observed ──────────────────────────────────────────────────────────────────────

def test_null_tracer_attempt_observed_returns_false() -> None:
    tracer = NullTracer()
    result = tracer.attempt_observed(RUN_ID, ATTEMPT_ID)
    assert result is False


def test_null_tracer_attempt_observed_returns_false_with_harness() -> None:
    tracer = NullTracer()
    result = tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="claude")
    assert result is False


def test_null_tracer_attempt_observed_returns_false_with_window() -> None:
    tracer = NullTracer()
    now = datetime.now(UTC)
    result = tracer.attempt_observed(
        RUN_ID, ATTEMPT_ID, started_at=now, ended_at=now
    )
    assert result is False


def test_null_tracer_attempt_observed_logs_trace_observed_disabled() -> None:
    """Structlog's `path="disabled"` and the shared `TRACE_OBSERVED` event name are logged."""
    tracer = NullTracer()
    with capture_logs() as logs:
        tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="claude")

    assert any(
        entry.get("event") == TRACE_OBSERVED and entry.get("path") == "disabled"
        for entry in logs
    ), logs


# ── trace_url ─────────────────────────────────────────────────────────────────────────────

def test_null_tracer_trace_url_returns_none() -> None:
    tracer = NullTracer()
    assert tracer.trace_url("any-trace-id") is None


def test_null_tracer_trace_url_returns_none_for_empty_string() -> None:
    tracer = NullTracer()
    assert tracer.trace_url("") is None


def test_null_tracer_trace_url_returns_none_for_run_id_hex() -> None:
    tracer = NullTracer()
    assert tracer.trace_url(RUN_ID.hex) is None


# ── protocol conformance ──────────────────────────────────────────────────────────────────

def test_null_tracer_is_a_tracer() -> None:
    assert isinstance(NullTracer(), Tracer)


def test_null_tracer_is_not_a_langfuse_tracer() -> None:
    assert not isinstance(NullTracer(), LangfuseTracer)


# ── unique span ids ───────────────────────────────────────────────────────────────────────

def test_null_tracer_step_span_each_entry_yields_unique_span_id() -> None:
    """Two entries must produce different span ids (fallback_span_ref uses uuid4)."""
    tracer = NullTracer()
    run = _run()
    with tracer.step_span(run, _row(), _attempt()) as s1:
        pass
    with tracer.step_span(run, _row(), _attempt()) as s2:
        pass
    assert s1.span_id != s2.span_id


# ── use-case rendering: AC 6 — NullTracer wired, trace_id present → None ─────────────────

def test_history_trace_url_is_none_when_null_tracer_and_trace_id_present() -> None:
    """`history.py::_trace_url` returns `None` when wired with `NullTracer` and `run.trace_id`
    is a non-empty string — the path `tracer is not None AND run.trace_id` in that function.

    This exercises AC 6 at the use-case output layer, not just the adapter method.
    """
    from orchestrator.application.use_cases.history import HistoryPorts, _trace_url

    class _StubHistoryQuery:
        """Minimal stand-in; `_trace_url` never touches `ports.history`."""

    run = _run(trace_id=RUN_ID.hex)  # trace_id is a non-empty string
    ports = HistoryPorts(history=_StubHistoryQuery(), tracer=NullTracer())  # type: ignore[arg-type]

    result = _trace_url(ports, run)

    assert result is None


def test_run_view_trace_url_is_none_when_null_tracer_and_trace_id_present() -> None:
    """The conditional at `run_views.py:334` evaluates to `None` when `NullTracer` is the
    tracer and `run.trace_id` is set — the specific branch `tracer is not None and run.trace_id`.

    Tested inline rather than through a full `RunViewPorts`: the conditional is a one-liner
    (`tracer.trace_url(run.trace_id) if (tracer is not None and run.trace_id) else None`) and
    the adapter method is what supplies the `None`.  This test proves both that the branch is
    taken (i.e., `tracer` and `trace_id` are not falsy) and that the result is `None`.
    """
    run = _run(trace_id=RUN_ID.hex)  # trace_id is truthy
    tracer: NullTracer | None = NullTracer()

    # Reproduce run_views.py:334 verbatim.
    result = tracer.trace_url(run.trace_id) if (tracer is not None and run.trace_id) else None

    assert result is None
    # Guard: ensure the else-branch was NOT taken (which would trivially produce None too).
    assert tracer is not None
    assert run.trace_id  # truthy — the real NullTracer.trace_url was reached
