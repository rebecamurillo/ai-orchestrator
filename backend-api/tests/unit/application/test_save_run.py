"""`create_run` with `save=True` (story 5-3): persists the plan but skips `engine.enqueue`.

AC coverage:
- save=True returns starts_now=False, waiting="saved — not started", engine_ref={}
- save=True does NOT call engine.enqueue
- save=False still enqueues (regression)
- save=True skips consent check when conflict_consent_required=True
- save=True still refuses fail lines (branch-held 409)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.queue import REASON_SAVED
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
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


def existing_run_on_different_branch() -> Run:
    """A non-terminal run on the same repository but a different branch."""
    return Run(
        id=new_id(),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="epic",
        template_version=1,
        status="running",
        inputs={"base_branch": "feat/other", "harness": "claude", "model": None},
        budget_usd=BUDGET,
        created_at=NOW,
        partition_branch="feat/other",
    )


def existing_run_on_same_branch() -> Run:
    """A non-terminal run on the same repository and same partition branch — causes fail line."""
    return Run(
        id=new_id(),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="epic",
        template_version=1,
        status="running",
        inputs={"base_branch": fixtures.INIT_BRANCH, "harness": "claude", "model": None},
        budget_usd=BUDGET,
        created_at=NOW,
        partition_branch=fixtures.INIT_BRANCH,
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


class SaveHarness:
    """Fakes wired for save-run tests."""

    def __init__(self, *, git: FakeGit, existing: list[Run] | None = None) -> None:
        self.runs = FakeRunRepository(existing or [])
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

    def create(self, request: CreateRunRequest) -> CreateRunResult:
        with self.uow:
            return create_run(self.ports, request)


# --- save=True: persists without enqueueing --------------------------------------------------


def test_save_true_returns_starts_now_false_and_reason_saved() -> None:
    harness = SaveHarness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))

    assert result.starts_now is False
    assert result.waiting == REASON_SAVED


def test_save_true_engine_ref_is_empty_dict() -> None:
    harness = SaveHarness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.engine_ref == {}


def test_save_true_does_not_call_engine_enqueue() -> None:
    harness = SaveHarness(git=fixtures.repo_init_git())

    harness.create(base_request(save=True))

    enqueue_calls = [name for name, _ in harness.engine.calls if name == "enqueue"]
    assert enqueue_calls == []


def test_save_true_status_is_queued() -> None:
    harness = SaveHarness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=True))

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.status == "queued"


# --- save=False still enqueues (regression) --------------------------------------------------


def test_save_false_still_enqueues() -> None:
    harness = SaveHarness(git=fixtures.repo_init_git())

    result = harness.create(base_request(save=False))

    enqueue_calls = [name for name, _ in harness.engine.calls if name == "enqueue"]
    assert len(enqueue_calls) == 1
    assert result.run.engine_ref != {}


# --- save=True skips consent check -----------------------------------------------------------


def test_save_true_skips_consent_check_when_conflict_consent_required() -> None:
    """save=True does not require conflict_consent even when a concurrent run is present."""
    harness = SaveHarness(
        git=fixtures.repo_init_git(),
        existing=[existing_run_on_different_branch()],
    )

    # conflict_consent=False but save=True → should succeed
    result = harness.create(base_request(save=True, conflict_consent=False))

    assert result is not None
    assert harness.runs.get(result.run.id) is not None


# --- save=True still refuses fail lines (branch held) ----------------------------------------


def test_save_true_refuses_branch_held_fail_line() -> None:
    """save=True still runs pre-flight and refuses if the branch is already held."""
    harness = SaveHarness(
        git=fixtures.repo_init_git(),
        existing=[existing_run_on_same_branch()],
    )

    with pytest.raises(Conflict):
        harness.create(base_request(save=True))
