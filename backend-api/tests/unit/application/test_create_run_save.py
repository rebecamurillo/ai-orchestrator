"""`create_run` with `save=True` (story 5-3): persist the plan but skip the engine enqueue.

A saved Run has `status="queued"` and `engine_ref={}`. The operator starts it later via
`POST /runs/{id}/start`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
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
    """One set of fakes, wired for create_run tests."""

    def __init__(self, *, git: FakeGit) -> None:
        self.runs = FakeRunRepository()
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


# ── save=True: persist the plan but skip the engine ──────────────────────────────────────


def test_save_true_skips_the_engine_and_leaves_engine_ref_empty() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))  # type: ignore[call-arg]

    assert result.run.engine_ref == {}  # type: ignore[union-attr]
    assert harness.engine.calls == []


def test_save_true_stores_the_run_as_queued() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))  # type: ignore[call-arg]

    stored = harness.runs.get(result.run.id)  # type: ignore[union-attr]
    assert stored is not None
    assert stored.status == "queued"


def test_save_true_sets_starts_now_false() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))  # type: ignore[call-arg]

    assert result.starts_now is False  # type: ignore[union-attr]


# ── save=False (default): existing behaviour is unchanged ────────────────────────────────


def test_save_false_enqueues_once_as_before() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request())

    assert harness.engine.calls == [
        ("enqueue", (result.run.id, f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"))  # type: ignore[union-attr]
    ]
