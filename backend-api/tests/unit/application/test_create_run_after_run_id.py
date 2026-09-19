"""`create_run` with `after_run_id` — dependency setup validation (story 5-4).

AC coverage:
- `after_run_id` without `save=True` raises `Conflict` (409).
- `after_run_id` with `save=True` stores the run with the dependency field set.
- A run created with `after_run_id` is NOT enqueued (engine_ref stays {}).
- `after_run_id=None` with `save=True` still works as the story 5-3 saved run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
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

    def create(self, **kwargs: object) -> object:
        req = CreateRunRequest(
            template_name="repo-init",
            template_version=1,
            project_id=fixtures.PROJECT.id,
            repository_id=fixtures.REPOSITORY.id,
            base_branch=fixtures.BASE_BRANCH,
            budget_usd=BUDGET,
            **kwargs,  # type: ignore[arg-type]
        )
        with self.uow:
            return create_run(self.ports, req)


# ── validation ─────────────────────────────────────────────────────────────────────────────


def test_after_run_id_without_save_raises_conflict() -> None:
    harness = Harness()
    predecessor_id = new_id()

    with pytest.raises(Conflict, match="after_run_id requires save=True"):
        harness.create(after_run_id=predecessor_id, save=False)


def test_after_run_id_with_save_false_is_the_default_and_raises() -> None:
    """save defaults to False, so after_run_id alone raises without explicitly setting save."""
    harness = Harness()

    with pytest.raises(Conflict):
        harness.create(after_run_id=new_id())


# ── stored run ─────────────────────────────────────────────────────────────────────────────


def test_after_run_id_with_save_stores_run_with_dependency_field() -> None:
    harness = Harness()
    predecessor_id = new_id()

    result = harness.create(after_run_id=predecessor_id, save=True)  # type: ignore[union-attr]

    run = harness.runs.get(result.run.id)  # type: ignore[union-attr]
    assert run is not None
    assert run.after_run_id == predecessor_id


def test_after_run_id_with_save_does_not_enqueue() -> None:
    harness = Harness()
    predecessor_id = new_id()

    result = harness.create(after_run_id=predecessor_id, save=True)  # type: ignore[union-attr]

    run = harness.runs.get(result.run.id)  # type: ignore[union-attr]
    assert run is not None
    assert run.engine_ref == {}
    assert not any(name == "enqueue" for name, _ in harness.engine.calls)


def test_save_without_after_run_id_still_works() -> None:
    """story 5-3 saved runs continue to work unchanged."""
    harness = Harness()

    result = harness.create(save=True)  # type: ignore[union-attr]

    run = harness.runs.get(result.run.id)  # type: ignore[union-attr]
    assert run is not None
    assert run.after_run_id is None
    assert run.engine_ref == {}
