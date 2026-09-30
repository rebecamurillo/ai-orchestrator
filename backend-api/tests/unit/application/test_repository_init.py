"""`init_repository` (SPEC CAP-10, FR-30): the Repository row's own action.

Reuses `create_run`'s own Harness shape (`test_create_run_use_case.py`) and the exemplar
Template fixtures the planner and pre-flight already build from, because this use case's
whole job is composing `create_run` with two extra refusals — proving it plans and persists
a whole tree is `create_run`'s own test, not this one's.

Which Template it starts is `InitRepositoryPorts.template_name`, the instance's
`INIT_TEMPLATE` (AD-20) — the fixture repository's own `repo-init` exemplar here, named as
test data and never read out of product code (Operator decision 2026-09-30: no template
name hardcoded in product code). The version is not configured at all: `init_repository`
resolves the *latest* stored version of that name at dispatch (AD-7, AD-15).
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
    InitRepositoryPorts,
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

#: The exemplar this suite configures the action with — fixture data, not a product name.
TEMPLATE_NAME = "repo-init"
#: The same exemplar text stored under a second name, so a test can prove the action
#: dispatches whatever `INIT_TEMPLATE` says rather than a name written into the product.
RENAMED_TEMPLATE = "house-init"


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
        "template_version": 1,
        "status": "running",
        "budget_usd": NO_BUDGET,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Harness:
    """The same wiring `test_create_run_use_case.py::Harness` gives `create_run`."""

    def __init__(
        self,
        *,
        repositories: list[Repository],
        existing: list[Run] | None = None,
        template_name: str = TEMPLATE_NAME,
    ):
        self.runs = FakeRunRepository(existing or [])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        stored = self.templates.versions[(TEMPLATE_NAME, 1)]
        self.templates.add(stored.model_copy(update={"name": RENAMED_TEMPLATE}))
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
        self.ports = InitRepositoryPorts(
            create_run=CreateRunPorts(
                preflight=preflight,
                engine=self.engine,
                steps=self.steps,
                uow=self.uow,
                clock=self.clock,
            ),
            template_name=template_name,
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
    # the latest stored version of the configured name, resolved at dispatch (AD-7, AD-15)
    assert stored.template_version == max(harness.templates.list_versions(TEMPLATE_NAME))
    assert stored.budget_usd == NO_BUDGET
    assert stored.inputs["base_branch"] == fixtures.REPOSITORY.default_branch
    assert stored.inputs["harness"] is not None  # `create_run`'s own default, never asked for
    # operator revision 2026-09-15: partition by (repository, branch)
    assert harness.engine.calls == [
        ("enqueue", (result.run.id, f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"))
    ]


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


# ── the Template is configuration, not a constant ─────────────────────────────────────────
# Operator decision 2026-09-30: no template name hardcoded in product code. These three
# replace the module constants `TEMPLATE_NAME`/`TEMPLATE_VERSION` the assertions above used
# to import from the use case, and assert more than they did: the *configured* name is what
# is dispatched and what the concurrency refusal is keyed on, and the version is resolved
# off the store rather than pinned.


def test_the_run_is_started_from_the_configured_template_whatever_it_is_called() -> None:
    harness = Harness(repositories=[repository()], template_name=RENAMED_TEMPLATE)

    result = harness.init(fixtures.REPOSITORY.id)

    assert result.run.template_name == RENAMED_TEMPLATE


def test_a_configured_template_nothing_stores_is_not_found() -> None:
    harness = Harness(repositories=[repository()], template_name="no-such-template")

    with pytest.raises(NotFound, match="no-such-template"):
        harness.init(fixtures.REPOSITORY.id)


def test_the_concurrency_refusal_follows_the_configured_name() -> None:
    """A running Run of the *configured* Template refuses; one of the shipped default's
    name, when that is not what is configured, does not."""
    running = a_run(template_name="epic", status="running")
    harness = Harness(repositories=[repository()], existing=[running], template_name="epic")

    with pytest.raises(Conflict, match=ALREADY_RUNNING.format(run_id=running.id)):
        harness.init(fixtures.REPOSITORY.id)
