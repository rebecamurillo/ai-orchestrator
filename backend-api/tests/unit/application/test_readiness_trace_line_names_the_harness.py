"""`evaluate`'s third line tells the tracer which harness it is asking about (7.2).

The trace check is not the same question for every harness (AD-10, AD-11): `claude` and
`codex` are proven by spans under the attempt span, and `codex` additionally accepts the
session-level evidence AD-11's universal floor leaves whenever `TRACEPARENT` is not honoured.
`Tracer.attempt_observed` can only apply the right rule if it is told which harness ran, and
`_trace_line` is the one caller that knows: the attempt itself carries it.

`Attempt.harness` is `str | None` — a row dispatched before a harness was recorded has none —
so the `None` case is asserted here too. It reaches the tracer as `None`, which is the strict
parented-only rule and the right default for a harness nobody can name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.use_cases.harness_readiness_evaluate import (
    CHECK_TRACE_OBSERVED,
    HarnessEvaluatePorts,
    _trace_line,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.tracer import FakeTracer

NOW = datetime(2026, 3, 4, tzinfo=UTC)
RUN_ID = new_id()


def a_ports(tracer: FakeTracer) -> HarnessEvaluatePorts:
    return HarnessEvaluatePorts(
        runs=FakeRunRepository([]),
        steps=FakeStepRunRepository([]),
        attempts=FakeAttemptRepository([]),
        harnesses=FakeHarnessRepository([]),
        projects=FakeProjectRepository([]),
        repositories=FakeRepositoryRepository([]),
        uow=FakeUnitOfWork(),
        clock=FakeClock(NOW),
        work_dir=Path("/work"),
        tracer=tracer,
    )


def an_attempt(harness: str | None) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=RUN_ID,
        step_run_id=new_id(),
        n=1,
        status="done",
        harness=harness,
        session_id="thread-1",
    )


@pytest.mark.parametrize("harness", ["codex", "claude", "local", None])
def test_the_attempts_own_harness_reaches_the_tracer(harness: str | None) -> None:
    tracer = FakeTracer()
    attempt = an_attempt(harness)

    _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert tracer.observed_calls == [(RUN_ID, attempt.id, harness)]


def test_the_line_still_reports_what_the_tracer_answered() -> None:
    tracer = FakeTracer()
    attempt = an_attempt("codex")
    tracer.observed[(RUN_ID, attempt.id)] = True

    line = _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert line.check == CHECK_TRACE_OBSERVED
    assert line.ok is True
    assert line.text == f"spans observed for attempt {attempt.id}"


def test_an_unobserved_attempt_keeps_the_wording_the_e2e_suite_pins() -> None:
    """`tests/e2e/test_harnesses.py` asserts this exact `failing_check` text; passing the
    harness through must not move it."""
    tracer = FakeTracer()
    attempt = an_attempt("codex")

    line = _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert line.ok is False
    assert line.text == f"no spans for attempt {attempt.id}"
