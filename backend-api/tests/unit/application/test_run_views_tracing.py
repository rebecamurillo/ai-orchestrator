"""`run_detail`'s `cost.trace_url` when a `Tracer` is wired (AD-11, 5.2's own Scope).

`test_run_views.py` (frozen) proves the opposite row of the matrix — no `trace_id`, no
`tracer` — stays `None` (`test_run_views.py:462`, whose own `a_run()` never sets
`trace_id`). This file proves the other one: a wired `FakeTracer` and a Run carrying a
`trace_id` answer `tracer.trace_url(run.trace_id)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.run_views import RunViewPorts, run_detail
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.fakes.tracer import FakeTracer

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=REPOSITORY_ID,
        project_id=PROJECT_ID,
        slug="acme-app",
        url="https://example.invalid/acme/app.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "inputs": {"base_branch": "main"},
        "status": "queued",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Harness:
    """Wired exactly like `test_run_views.py`'s own `Harness`, plus a `Tracer`."""

    def __init__(self, *, tracer: FakeTracer | None) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gate_records = FakeGateRecordRepository()
        self.projects = FakeProjectRepository([project()])
        self.repositories = FakeRepositoryRepository([repository()])
        self.logs = FakeLogReader()
        self.clock = FakeClock(NOW)
        self.tracer = tracer

    def ports(self) -> RunViewPorts:
        return RunViewPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            gate_records=self.gate_records,
            projects=self.projects,
            repositories=self.repositories,
            logs=self.logs,
            clock=self.clock,
            tracer=self.tracer,
        )


def test_trace_url_is_the_tracers_answer_when_wired_and_the_run_has_a_trace_id() -> None:
    tracer = FakeTracer()
    harness = Harness(tracer=tracer)
    run = a_run(status="running", trace_id="t-1")
    harness.runs.add(run)

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.trace_url == tracer.trace_url("t-1")


def test_trace_url_is_none_when_the_run_has_no_trace_id_even_with_a_tracer_wired() -> None:
    harness = Harness(tracer=FakeTracer())
    run = a_run(status="running")
    harness.runs.add(run)

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.trace_url is None


def test_trace_url_is_none_when_no_tracer_is_wired_even_with_a_trace_id() -> None:
    harness = Harness(tracer=None)
    run = a_run(status="running", trace_id="t-1")
    harness.runs.add(run)

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.trace_url is None
