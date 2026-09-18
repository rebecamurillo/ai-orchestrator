"""`create_run` consent enforcement (story 5-2: shared-repository informed consent).

Tests that `create_run` raises `Conflict` when `conflict_consent_required` is true and
`conflict_consent` is false, passes when consent is given, and ignores the flag when no
concurrent warn is present.

The concurrent warn is triggered by pre-seeding a non-terminal Run on the same Repository
with a different `partition_branch`.  `repo-init@1` creates branch `chore/bmad-init`, so a
pre-existing run with any other branch (here `feat/other`) causes `concurrent_repo_lines`
to emit a warn and sets `conflict_consent_required` to true.
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
from orchestrator.domain.entities.run import Run
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


class ConsentHarness:
    """Fakes wired for consent tests.

    `pre_existing` seeds the run repository before the test call so that
    `concurrent_repo_lines` finds a concurrent run and `conflict_consent_required` is set.
    """

    def __init__(self, *, pre_existing: list[Run] | None = None) -> None:
        self.runs = FakeRunRepository(pre_existing or [])
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


# --- consent required but missing → 409 --------------------------------------------------


def test_create_run_raises_conflict_when_consent_required_and_not_given() -> None:
    harness = ConsentHarness(pre_existing=[existing_run_on_different_branch()])

    with pytest.raises(Conflict) as exc_info:
        harness.create(base_request(conflict_consent=False))

    assert "this can lead to merge conflicts" in str(exc_info.value)


# --- consent given → run created (201) ---------------------------------------------------


def test_create_run_succeeds_when_consent_is_given_and_warn_present() -> None:
    harness = ConsentHarness(pre_existing=[existing_run_on_different_branch()])

    result = harness.create(base_request(conflict_consent=True))

    assert result is not None  # type: ignore[union-attr]
    # verify the new run was persisted
    assert harness.runs.get(result.run.id) is not None  # type: ignore[union-attr]


# --- no concurrent run → consent flag ignored --------------------------------------------


def test_create_run_succeeds_with_consent_false_when_no_concurrent_run() -> None:
    harness = ConsentHarness(pre_existing=[])

    result = harness.create(base_request(conflict_consent=False))

    assert result is not None  # type: ignore[union-attr]
