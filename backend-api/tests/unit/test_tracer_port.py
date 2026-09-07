"""The `Tracer` port's shape, and the one fake that satisfies it (AD-11, AD-18).

`isinstance` against the protocol is what lets 5.4/5.8 test an executor or a readiness rule
against `FakeTracer` and be sure it is the same thing a real `LangfuseTracer` is to a caller.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.tracer import SpanRef, Tracer, TraceRef
from tests.unit.fakes.tracer import FakeTracer, trace_id_of

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000002")
REPOSITORY_ID = UUID("00000000-0000-0000-0000-000000000003")
STEP_RUN_ID = UUID("00000000-0000-0000-0000-000000000004")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-000000000005")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def a_run() -> Run:
    return Run(
        id=RUN_ID,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=NOW,
    )


def a_row() -> StepRun:
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


def an_attempt() -> Attempt:
    return Attempt(id=ATTEMPT_ID, run_id=RUN_ID, step_run_id=STEP_RUN_ID, n=1, status="running")


def test_a_trace_ref_carries_the_id_and_is_frozen() -> None:
    ref = TraceRef(trace_id="t-1")

    assert ref.trace_id == "t-1"
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass, exact type varies
        ref.trace_id = "t-2"  # type: ignore[misc]


def test_a_span_ref_carries_its_ids_and_traceparent_and_is_frozen() -> None:
    span = SpanRef(
        trace_id="t-1", span_id="0000000000000001", traceparent="00-t-1-0000000000000001-01"
    )

    assert span.trace_id == "t-1"
    assert span.span_id == "0000000000000001"
    assert span.traceparent == "00-t-1-0000000000000001-01"
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass, exact type varies
        span.span_id = "x"  # type: ignore[misc]


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeTracer(), Tracer)


def test_create_run_trace_is_recorded_and_deterministic_by_run_id() -> None:
    fake = FakeTracer()

    ref = fake.create_run_trace(RUN_ID, "proj", (), name="run repo-init@1 main")

    assert ref.trace_id == trace_id_of(RUN_ID)
    assert fake.create_run_trace_calls == [(RUN_ID, "proj", (), "run repo-init@1 main")]


def test_step_span_is_a_context_manager_that_records_and_yields_a_span_ref() -> None:
    fake = FakeTracer()
    run, row, attempt = a_run(), a_row(), an_attempt()

    with fake.step_span(run, row, attempt) as span:
        assert span.trace_id == trace_id_of(RUN_ID)
        assert span.traceparent == f"00-{trace_id_of(RUN_ID)}-{span.span_id}-01"

    assert fake.step_span_calls == [(RUN_ID, "stories[0].build", ATTEMPT_ID)]


def test_attempt_span_is_a_context_manager_that_records_and_yields_a_span_ref() -> None:
    fake = FakeTracer()
    run, row, attempt = a_run(), a_row(), an_attempt()

    with fake.attempt_span(run, row, attempt) as span:
        assert span.trace_id == trace_id_of(RUN_ID)

    assert fake.attempt_span_calls == [(RUN_ID, "stories[0].build", ATTEMPT_ID)]


def test_each_span_call_gets_its_own_span_id() -> None:
    fake = FakeTracer()
    run, row, attempt = a_run(), a_row(), an_attempt()

    with fake.step_span(run, row, attempt) as first:
        pass
    with fake.attempt_span(run, row, attempt) as second:
        pass

    assert first.span_id != second.span_id


def test_attempt_observed_answers_the_scripted_value() -> None:
    fake = FakeTracer()
    fake.observed[(RUN_ID, ATTEMPT_ID)] = True

    assert fake.attempt_observed(RUN_ID, ATTEMPT_ID) is True


def test_attempt_observed_answers_false_for_an_unscripted_pair() -> None:
    fake = FakeTracer()

    assert fake.attempt_observed(RUN_ID, ATTEMPT_ID) is False


def test_trace_url_answers_a_url_naming_the_trace_id() -> None:
    fake = FakeTracer()

    url = fake.trace_url("t-1")

    assert "t-1" in url
