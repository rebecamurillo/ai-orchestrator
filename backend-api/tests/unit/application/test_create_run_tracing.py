"""`create_run` opens the Run's trace (AD-11, 5.2's own Scope).

Reuses the shipped-Template fixtures `tests/unit/application/templates/plan_fixtures.py`
already builds, exactly as `test_create_run_use_case.py` does — this file only adds the
`Tracer` half `test_create_run_use_case.py` (frozen, predates this story) never wires.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository
from tests.unit.fakes.tracer import FakeTracer, trace_id_of

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")


def project() -> Project:
    return Project(
        id=fixtures.PROJECT.id,
        slug=fixtures.PROJECT.slug,
        name=fixtures.PROJECT.name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=fixtures.REPOSITORY.id,
        project_id=fixtures.PROJECT.id,
        slug=fixtures.REPOSITORY.slug,
        url=fixtures.REPOSITORY.url,
        default_branch=fixtures.REPOSITORY.default_branch,
        install_command=fixtures.REPOSITORY.install_command or "",
        quality_gate_command=fixtures.REPOSITORY.quality_gate_command or "",
        unit_test_command=fixtures.REPOSITORY.unit_test_command or "",
        test_globs=fixtures.REPOSITORY.test_globs,
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version=fixtures.BMAD_VERSION),
        created_at=NOW,
        updated_at=NOW,
    )


def base_request(**overrides: object) -> CreateRunRequest:
    payload: dict[str, object] = {
        "template_name": "repo-init",
        "template_version": 1,
        "project_id": fixtures.PROJECT.id,
        "repository_id": fixtures.REPOSITORY.id,
        "base_branch": fixtures.BASE_BRANCH,
        "budget_usd": BUDGET,
    }
    payload.update(overrides)
    return CreateRunRequest(**payload)  # type: ignore[arg-type]


class Harness:
    """One set of fakes, wired the way `api/providers.py::create_run_ports` wires them —
    `tracer` added, which `test_create_run_use_case.py`'s own `Harness` never sets."""

    def __init__(self, *, git: FakeGit, tracer: FakeTracer | None) -> None:
        self.runs = FakeRunRepository()
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        self.tracer = tracer
        preflight = PreflightPorts(
            git=git,
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
        )
        self.ports = CreateRunPorts(
            preflight=preflight,
            engine=self.engine,
            steps=self.steps,
            uow=self.uow,
            clock=self.clock,
            tracer=tracer,
        )

    def create(self, request: CreateRunRequest) -> CreateRunResult:
        with self.uow:
            return create_run(self.ports, request)


def test_create_run_with_a_tracer_opens_the_trace_and_stores_the_id() -> None:
    tracer = FakeTracer()
    harness = Harness(git=fixtures.repo_init_git(), tracer=tracer)

    result = harness.create(base_request())

    assert len(tracer.create_run_trace_calls) == 1
    called_run_id, called_slug, called_tags, called_name = tracer.create_run_trace_calls[0]
    assert called_run_id == result.run.id
    assert called_slug == fixtures.PROJECT.slug
    assert called_tags == ()
    assert called_name == f"run repo-init@1 {fixtures.BASE_BRANCH}"
    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.trace_id == trace_id_of(result.run.id)


def test_create_run_with_no_tracer_leaves_trace_id_none_and_still_creates() -> None:
    harness = Harness(git=fixtures.repo_init_git(), tracer=None)

    result = harness.create(base_request())

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.trace_id is None
    assert stored.status == "queued"
