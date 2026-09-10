"""`evaluate`'s third line also tells the tracer *when* the attempt ran (AD-11, 7.3).

7.2 gave `attempt_observed` the harness, because the rule differs per harness. 7.3 gives it
the window, because `local`'s rule *is* a window: the OpenCode Langfuse plugin carries no
attempt id — one trace per turn, keyed by OpenCode's own session, with `userId = run_id`
(`research/tracing.md` §OpenCode) — so what separates this attempt's generations from another
attempt of the same Run is when they happened, and `Attempt` is the only object that knows.

`_trace_line` is the one caller that holds the attempt, exactly as it is the one that holds
the harness. Both halves are keyword-only and defaulted on the port, so no other call site and
no frozen test moves; this module is what says the values actually arrive.

`started_at`/`ended_at` are `datetime | None` on the entity — an attempt whose start half was
written and whose end half was not is an ordinary stored state (AD-8) — so the `None` cases
are asserted here too. They reach the tracer as `None`, and the adapter's own rule is what
declines to accept an unattributable generation as evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

NOW = datetime(2026, 9, 10, tzinfo=UTC)
STARTED = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
ENDED = STARTED + timedelta(minutes=20)
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


def an_attempt(**overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": RUN_ID,
        "step_run_id": new_id(),
        "n": 1,
        "status": "done",
        "harness": "local",
        "session_id": "ses_7f3c1a0b9d2e4f5a",
        "started_at": STARTED,
        "ended_at": ENDED,
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_the_attempts_own_window_reaches_the_tracer() -> None:
    tracer = FakeTracer()

    _trace_line(a_ports(tracer), RUN_ID, an_attempt())

    assert tracer.observed_windows == [(STARTED, ENDED)]


@pytest.mark.parametrize("missing", ["started_at", "ended_at"])
def test_a_half_written_attempt_reaches_the_tracer_as_the_absence_it_is(missing: str) -> None:
    """AD-8 writes an attempt in two halves; a backend restart between them leaves one of
    these `None`. It is passed through as `None` rather than substituted with a time this
    use case invented."""
    tracer = FakeTracer()

    _trace_line(a_ports(tracer), RUN_ID, an_attempt(**{missing: None}))

    assert tracer.observed_windows[0][["started_at", "ended_at"].index(missing)] is None


def test_the_harness_still_reaches_the_tracer_beside_it() -> None:
    """7.2's own assertion, restated over a `local` attempt: adding the window must not have
    displaced the name the rule is chosen by."""
    tracer = FakeTracer()
    attempt = an_attempt()

    _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert tracer.observed_calls == [(RUN_ID, attempt.id, "local")]


def test_the_line_still_reports_what_the_tracer_answered() -> None:
    tracer = FakeTracer()
    attempt = an_attempt()
    tracer.observed[(RUN_ID, attempt.id)] = True

    line = _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert line.check == CHECK_TRACE_OBSERVED
    assert line.ok is True
    assert line.text == f"spans observed for attempt {attempt.id}"


def test_an_unobserved_local_attempt_keeps_the_wording_the_e2e_suite_pins() -> None:
    """`tests/e2e/test_harnesses.py` asserts this exact `failing_check` text for every
    harness; passing a window through must not move it."""
    tracer = FakeTracer()
    attempt = an_attempt()

    line = _trace_line(a_ports(tracer), RUN_ID, attempt)

    assert line.ok is False
    assert line.text == f"no spans for attempt {attempt.id}"
