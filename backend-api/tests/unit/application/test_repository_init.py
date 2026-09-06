"""`init_repository` (SPEC CAP-10, FR-30): the Repository row's own action.

Reuses `create_run`'s own Harness shape (`test_create_run_use_case.py`) and the
shipped-Template fixtures the planner and pre-flight already build from, because this use
case's whole job is composing `create_run` with two extra refusals — proving it plans and
persists the real `repo-init@1` tree is `create_run`'s own test, not this one's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.repositories import (
    ALREADY_RUNNING,
    CLONE_CHECK_FAILED,
    NO_BUDGET,
    TEMPLATE_NAME,
    TEMPLATE_VERSION,
    init_repository,
)
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
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
        "clone_check": CloneCheck(
            status="ok", at=NOW, output="", bmad_version=fixtures.BMAD_VERSION
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": fixtures.PROJECT.id,
        "repository_id": fixtures.REPOSITORY.id,
        "template_name": TEMPLATE_NAME,
        "template_version": TEMPLATE_VERSION,
        "status": "running",
        "budget_usd": NO_BUDGET,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Harness:
    """The same wiring `test_create_run_use_case.py::Harness` gives `create_run`."""

    def __init__(self, *, repositories: list[Repository], existing: list[Run] | None = None):
        self.runs = FakeRunRepository(existing or [])
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
            repositories=FakeRepositoryRepository(repositories),
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

    def init(self, repository_id: object) -> object:
        with self.uow:
            return init_repository(self.ports, repository_id)  # type: ignore[arg-type]


def test_a_missing_method_and_a_passing_clone_check_starts_repo_init() -> None:
    harness = Harness(repositories=[repository()])

    result = harness.init(fixtures.REPOSITORY.id)

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.template_name == TEMPLATE_NAME
    assert stored.template_version == TEMPLATE_VERSION
    assert stored.budget_usd == NO_BUDGET
    assert stored.inputs["base_branch"] == fixtures.REPOSITORY.default_branch
    assert stored.inputs["harness"] is not None  # `create_run`'s own default, never asked for
    assert harness.engine.calls == [("enqueue", (result.run.id, fixtures.REPOSITORY.id))]


def test_an_unknown_repository_is_not_found() -> None:
    harness = Harness(repositories=[])

    with pytest.raises(NotFound):
        harness.init(fixtures.REPOSITORY.id)


def test_a_failed_clone_check_refuses_with_the_fixed_sentence() -> None:
    harness = Harness(
        repositories=[
            repository(
                clone_check=CloneCheck(
                    status="failed",
                    at=NOW,
                    output="fatal: Authentication failed",
                    bmad_version=None,
                )
            )
        ]
    )

    with pytest.raises(Conflict, match=CLONE_CHECK_FAILED):
        harness.init(fixtures.REPOSITORY.id)


def test_a_non_terminal_repo_init_run_already_on_this_repository_refuses() -> None:
    running = a_run(status="running")
    harness = Harness(repositories=[repository()], existing=[running])

    with pytest.raises(Conflict, match=ALREADY_RUNNING.format(run_id=running.id)):
        harness.init(fixtures.REPOSITORY.id)


def test_a_non_terminal_run_of_a_different_template_does_not_block_it() -> None:
    other = a_run(template_name="epic", status="running")
    harness = Harness(repositories=[repository()], existing=[other])

    result = harness.init(fixtures.REPOSITORY.id)

    assert result.run.template_name == TEMPLATE_NAME


def test_a_terminal_repo_init_run_does_not_block_a_second_one() -> None:
    done = a_run(status="done")
    harness = Harness(repositories=[repository()], existing=[done])

    result = harness.init(fixtures.REPOSITORY.id)

    assert result.run.id != done.id
    assert result.run.template_name == TEMPLATE_NAME
