"""`create_run` with `budget_usd=None` — null-budget run creation (story 3-2, AC1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
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

NOW = datetime(2026, 1, 1, tzinfo=UTC)


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


class Harness:
    def __init__(self, *, git: FakeGit) -> None:
        self.runs = FakeRunRepository([])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
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
        )

    def create(self, request: CreateRunRequest) -> object:
        with self.uow:
            return create_run(self.ports, request)


def test_create_run_with_null_budget_succeeds_and_stores_null() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    request = CreateRunRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        budget_usd=None,
    )

    result = harness.create(request)

    stored = harness.runs.get(result.run.id)  # type: ignore[union-attr]
    assert stored is not None
    assert stored.budget_usd is None
