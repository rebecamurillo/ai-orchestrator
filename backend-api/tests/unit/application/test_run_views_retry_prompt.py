"""`StepRowView.retry_prompt` derived from `with_resolved` (story 3-5).

The I/O matrix: `retry_prompt` equals `with_resolved["retry"]["prompt"]` when the key is
present and the value is a string; `None` when the retry block is absent, when
`with_resolved["retry"]` is not a dict, or when the prompt key is absent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.run_views import (
    RunViewPorts,
    run_detail,
)
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
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

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


def _project() -> Project:
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


def _repository() -> Repository:
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


def _a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="story",
        template_version=1,
        inputs={"base_branch": "main"},
        status="queued",
        budget_usd=Decimal("10"),
        created_at=NOW,
    )


def _a_row(run: Run, *, with_resolved: dict) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="build",
        label="build",
        kind="agent",
        gate="liveness",
        status="planned",
        with_resolved=with_resolved,
    )


def _ports(run: Run, row: StepRun) -> RunViewPorts:
    runs = FakeRunRepository()
    runs.add(run)
    steps = FakeStepRunRepository()
    steps.add_many([row])
    return RunViewPorts(
        runs=runs,
        steps=steps,
        attempts=FakeAttemptRepository(),
        gate_records=FakeGateRecordRepository(),
        projects=FakeProjectRepository([_project()]),
        repositories=FakeRepositoryRepository([_repository()]),
        logs=FakeLogReader(),
        clock=FakeClock(NOW),
    )


def test_retry_prompt_is_read_from_with_resolved_when_present() -> None:
    run = _a_run()
    row = _a_row(run, with_resolved={"retry": {"max": 1, "prompt": "expected-text"}})
    ports = _ports(run, row)

    detail = run_detail(ports, run.id)

    assert detail.steps[0].retry_prompt == "expected-text"


def test_retry_prompt_is_none_when_no_retry_block() -> None:
    run = _a_run()
    row = _a_row(run, with_resolved={})
    ports = _ports(run, row)

    detail = run_detail(ports, run.id)

    assert detail.steps[0].retry_prompt is None


def test_retry_prompt_is_none_when_retry_is_not_a_dict() -> None:
    run = _a_run()
    row = _a_row(run, with_resolved={"retry": "not-a-dict"})
    ports = _ports(run, row)

    detail = run_detail(ports, run.id)

    assert detail.steps[0].retry_prompt is None


def test_retry_prompt_is_none_when_prompt_key_absent() -> None:
    run = _a_run()
    row = _a_row(run, with_resolved={"retry": {"max": 1}})
    ports = _ports(run, row)

    detail = run_detail(ports, run.id)

    assert detail.steps[0].retry_prompt is None
