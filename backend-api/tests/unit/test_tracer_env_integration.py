"""`Tracer.attempt_span`'s `traceparent` reaches `env_for` and comes out as `TRACEPARENT`
in the env a harness receives (AD-11, the brief's own AC #2) — the mechanism 5.4 wires for
real; proved once here since no production `agent` executor exists before then.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.env import env_for
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.tracer import FakeTracer, trace_id_of

PROJECT_SLUG = "acme"


def test_the_attempt_spans_traceparent_appears_verbatim_as_traceparent_in_the_env(
    env: dict[str, str],
) -> None:
    settings = Settings()
    run = Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=datetime(2026, 9, 7, tzinfo=UTC),
    )
    row = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
    )
    attempt = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=1,
        status="running",
        harness="claude",
    )
    tracer = FakeTracer()
    harness = FakeHarness()

    with tracer.attempt_span(run, row, attempt) as span:
        assert span.trace_id == trace_id_of(run.id)
        assert span.traceparent == f"00-{trace_id_of(run.id)}-{span.span_id}-01"

        built_env = env_for(
            attempt,
            run=run,
            project_slug=PROJECT_SLUG,
            project_env={},
            log_content=False,
            settings=settings,
            traceparent=span.traceparent,
        )
        # Operator revision 2026-09-15: agent steps no longer carry a 90-min wall-clock
        # default; `timeout_min=None` means no deadline (stall detection is the guard instead).
        harness.run(
            cwd=Path("/work/wt/a"),
            prompt="build story 5-1",
            env=built_env,
            model=None,
            session_id="s-1",
            budget_usd_remaining=Decimal("10"),
            timeout_min=None,
            log_path=Path("/work/logs/a.log"),
        )

    assert harness.calls[0]["env"]["TRACEPARENT"] == span.traceparent
