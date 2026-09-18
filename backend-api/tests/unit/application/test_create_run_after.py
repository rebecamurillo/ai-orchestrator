"""`create_run` with `after_run_id` (story 5-4).

`after_run_id` is a new optional field on `CreateRunRequest`.  It is only valid when
`save=True`.  When both are provided:
- the Run is stored with `after_run_id` set and `engine_ref = {}`
- `starts_now` is `False`
- `waiting` is `"waiting for run <uuid>"`
- `engine.enqueue` is NOT called

When `after_run_id` is provided but `save=False`, a `Conflict` is raised.
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
from orchestrator.application.use_cases.queue import REASON_WAITING_DEPENDENCY
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
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


def _project() -> Project:
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


def _repository() -> Repository:
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


class AfterRunHarness:
    """Fakes wired for after_run_id tests."""

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
            repositories=FakeRepositoryRepository([_repository()]),
            projects=FakeProjectRepository([_project()]),
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

    def create(self, request: CreateRunRequest):
        with self.uow:
            return create_run(self.ports, request)


def _base_request(**overrides) -> CreateRunRequest:
    payload = {
        "template_name": "repo-init",
        "template_version": 1,
        "project_id": fixtures.PROJECT.id,
        "repository_id": fixtures.REPOSITORY.id,
        "base_branch": fixtures.BASE_BRANCH,
        "budget_usd": BUDGET,
    }
    payload.update(overrides)
    return CreateRunRequest(**payload)  # type: ignore[arg-type]


# ── after_run_id + save=True ─────────────────────────────────────────────────


def test_after_run_id_with_save_true_stores_after_run_id() -> None:
    """Run is stored with after_run_id set when save=True and after_run_id is provided."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    result = harness.create(_base_request(save=True, after_run_id=predecessor_id))

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.after_run_id == predecessor_id


def test_after_run_id_with_save_true_returns_starts_now_false() -> None:
    """starts_now is False for a dependency-waiting saved Run."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    result = harness.create(_base_request(save=True, after_run_id=predecessor_id))

    assert result.starts_now is False


def test_after_run_id_with_save_true_returns_waiting_dependency_reason() -> None:
    """waiting is 'waiting for run <uuid>' when after_run_id is set."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    result = harness.create(_base_request(save=True, after_run_id=predecessor_id))

    expected = REASON_WAITING_DEPENDENCY.format(x=str(predecessor_id))
    assert result.waiting == expected


def test_after_run_id_with_save_true_does_not_enqueue() -> None:
    """engine.enqueue is NOT called for a dependency-waiting Run."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    harness.create(_base_request(save=True, after_run_id=predecessor_id))

    enqueue_calls = [name for name, _ in harness.engine.calls if name == "enqueue"]
    assert enqueue_calls == []


def test_after_run_id_with_save_true_engine_ref_is_empty() -> None:
    """The stored Run has engine_ref={} (not yet dispatched)."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    result = harness.create(_base_request(save=True, after_run_id=predecessor_id))

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.engine_ref == {}


# ── after_run_id without save=True → Conflict ────────────────────────────────


def test_after_run_id_without_save_raises_conflict() -> None:
    """after_run_id without save=True is a 409 Conflict."""
    predecessor_id = new_id()
    harness = AfterRunHarness(git=fixtures.repo_init_git())

    with pytest.raises(Conflict):
        harness.create(_base_request(save=False, after_run_id=predecessor_id))
