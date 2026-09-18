"""`create_run._partition_branch` (story 5-1, AD-12): the helper that picks the declared
branch from the plan, and `create_run`'s use of it to set `run.partition_branch` and to
build the `engine.enqueue` partition key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.templates.plan_model import Plan
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    _partition_branch,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("5.00")


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


def repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": fixtures.REPOSITORY.id,
        "project_id": fixtures.PROJECT.id,
        "slug": fixtures.REPOSITORY.slug,
        "url": fixtures.REPOSITORY.url,
        "default_branch": fixtures.REPOSITORY.default_branch,
        "install_command": fixtures.REPOSITORY.install_command or "",
        "quality_gate_command": fixtures.REPOSITORY.quality_gate_command or "",
        "unit_test_command": fixtures.REPOSITORY.unit_test_command or "",
        "test_globs": fixtures.REPOSITORY.test_globs,
        "package_manager": "uv",
        "clone_check": CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


class Harness:
    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
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


# ── _partition_branch helper ──────────────────────────────────────────────────


def test_partition_branch_returns_first_declared_key_for_story_plan() -> None:
    """A story/epic plan has one branches entry: {declared: created}."""
    plan = Plan(plan_ref="sha", rows=(), branches={"feat/topic": "feat/topic-1"})

    assert _partition_branch(plan, "main") == "feat/topic"


def test_partition_branch_returns_base_branch_for_initiative_empty_branches() -> None:
    """An initiative plan has no branch declarations; base_branch is the partition key."""
    plan = Plan(plan_ref="sha", rows=(), branches={})

    assert _partition_branch(plan, "main") == "main"


def test_partition_branch_uses_first_key_when_multiple_branches_declared() -> None:
    """If a template ever declares more than one branch, the first key is the partition."""
    plan = Plan(plan_ref="sha", rows=(), branches={"feat/a": "feat/a-1", "feat/b": "feat/b-1"})

    assert _partition_branch(plan, "main") == "feat/a"


# ── create_run sets run.partition_branch and partition key ───────────────────


def test_create_run_sets_partition_branch_to_declared_branch() -> None:
    """run.partition_branch equals the first declared branch in the plan (story 5-1)."""
    harness = Harness()
    request = CreateRunRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        budget_usd=BUDGET,
    )

    result = harness.create(request)

    assert result.run.partition_branch == fixtures.INIT_BRANCH  # type: ignore[attr-defined]


def test_create_run_enqueues_with_repository_colon_declared_branch_key() -> None:
    """engine.enqueue receives f"{repository_id}:{declared_branch}" (AD-12, story 5-1)."""
    harness = Harness()
    request = CreateRunRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        budget_usd=BUDGET,
    )

    result = harness.create(request)

    run_id = result.run.id  # type: ignore[attr-defined]
    expected_key = f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"
    assert harness.engine.calls == [("enqueue", (run_id, expected_key))]
