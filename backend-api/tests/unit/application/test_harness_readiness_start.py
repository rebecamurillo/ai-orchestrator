"""`harness_readiness.start` (SPEC CAP-8): dispatch one readiness Run.

The happy path configures `HarnessReadinessPorts.template_name` with the fixture
repository's own `repo-init` exemplar (Operator decision 2026-09-30: no template name
hardcoded in product code — the name is test data here, never read out of the product):
`create_run`'s own planning of that Template is already thoroughly proven by
`tests/unit/application/test_create_run_use_case.py`, and it needs no list file at all
(`plan_fixtures.repo_init_git`'s own docstring), so this suite can prove `start`'s
own wiring — which Project/Repository it resolves, the budget, `skip_harness_check`, the
branch it computes, the 404/409 refusals — without re-proving `create_run`'s planning a
second time over a heavier Template.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases import harness_readiness
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.harness_readiness import (
    HarnessReadinessPorts,
    _free_branch,
    _readiness_repository,
    start,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)
BUDGET = Decimal("5")
TODAY = date(2026, 3, 4)

#: The exemplar every test here configures readiness with — see the module docstring.
TEMPLATE_NAME = "repo-init"


def readiness_project() -> Project:
    return Project(
        id=new_id(),
        slug=READINESS_PROJECT_SLUG,
        name="Readiness",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=True,
        created_at=NOW,
        updated_at=NOW,
    )


def readiness_repository(project_id: UUID) -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
        slug=harness_readiness.READINESS_REPOSITORY_SLUG,
        url="file:///work/readiness/origin.git",
        default_branch="main",
        install_command="",
        quality_gate_command="sh check.sh",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck(
            status="ok", at=NOW, output="ok", bmad_version=fixtures.BMAD_VERSION
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def _readiness_git() -> FakeGit:
    """A remote holding `main` and `specs/readiness/SPEC.md`, and not the branch `start`
    would create — `plan_fixtures.repo_init_git`'s own shape, plus the one file pre-flight's
    `CHECK_SPEC_MD` line reads regardless of which Template is under test."""
    return FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
        files={(fixtures.BASE_SHA, "specs/readiness/SPEC.md"): "# readiness fixture"},
        listings={},
    )


class World:
    """Fakes wired the way `api/providers.py::readiness_ports` wires them."""

    def __init__(
        self,
        *,
        project: Project | None = None,
        existing_runs: list[Run] | None = None,
        template_name: str = TEMPLATE_NAME,
    ) -> None:
        self.project = project if project is not None else readiness_project()
        self.repository = readiness_repository(self.project.id)
        self.projects = FakeProjectRepository([self.project])
        self.repositories = FakeRepositoryRepository([self.repository])
        self.runs = FakeRunRepository(existing_runs or [])
        self.templates = fixtures.FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        preflight = PreflightPorts(
            git=_readiness_git(),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=self.repositories,
            projects=self.projects,
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=fixtures.BASE.parent.parent.parent,
        )
        self.ports = HarnessReadinessPorts(
            create_run=CreateRunPorts(
                preflight=preflight,
                engine=self.engine,
                steps=self.steps,
                uow=self.uow,
                clock=self.clock,
                skip_harness_check=True,
            ),
            budget_usd=BUDGET,
            template_name=template_name,
        )

    def start(self, name: str) -> object:
        with self.uow:
            return start(self.ports, name)


# ── the happy path ────────────────────────────────────────────────────────────────────────


def test_dispatches_on_the_readiness_project_and_repository_with_the_budget_and_harness() -> None:
    world = World()

    result = world.start("claude")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.project_id == world.project.id
    assert stored.repository_id == world.repository.id
    assert stored.budget_usd == BUDGET
    assert stored.inputs["harness"] == "claude"
    assert stored.inputs["branch"] == "readiness/claude/2026-03-04"
    assert stored.inputs["spec_folder"] == "specs/readiness"
    assert stored.status == "queued"


def test_skip_harness_check_lets_a_never_enabled_harness_run_its_own_readiness_run() -> None:
    """`FakeHarnessRepository()` above stores no harness at all — disabled, in pre-flight
    terms — and `start` must dispatch anyway (AD-10's carried-forward flag)."""
    world = World()

    result = world.start("claude")

    assert world.runs.get(result.run.id) is not None


# ── refusals ──────────────────────────────────────────────────────────────────────────────


def test_refuses_not_found_when_the_readiness_project_is_not_seeded() -> None:
    world = World()
    world.projects.projects.clear()

    with pytest.raises(NotFound, match="Project"):
        world.start("claude")


def test_refuses_not_found_when_the_readiness_repository_is_not_seeded() -> None:
    world = World()
    world.repositories.repositories.clear()

    with pytest.raises(NotFound, match="Repository"):
        world.start("claude")


def test_refuses_conflict_when_a_non_terminal_readiness_run_for_the_harness_exists() -> None:
    world = World()
    in_flight = Run(
        id=new_id(),
        project_id=world.project.id,
        repository_id=world.repository.id,
        template_name="repo-init",
        template_version=1,
        inputs={"harness": "claude", "branch": "readiness/claude/2026-03-03"},
        status="running",
        budget_usd=BUDGET,
        created_at=NOW,
    )
    world.runs.add(in_flight)

    with pytest.raises(Conflict, match="claude"):
        world.start("claude")


def test_a_non_terminal_run_for_a_different_harness_does_not_conflict() -> None:
    world = World()
    other = Run(
        id=new_id(),
        project_id=world.project.id,
        repository_id=world.repository.id,
        template_name="repo-init",
        template_version=1,
        inputs={"harness": "codex", "branch": "readiness/codex/2026-03-04"},
        status="running",
        budget_usd=BUDGET,
        created_at=NOW,
    )
    world.runs.add(other)

    result = world.start("claude")

    assert world.runs.get(result.run.id) is not None


# ── `_free_branch` (pure) ────────────────────────────────────────────────────────────────


def _run_with(*, harness: str, branch: str) -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="repo-init",
        template_version=1,
        inputs={"harness": harness, "branch": branch},
        status="running",
        budget_usd=BUDGET,
        created_at=NOW,
    )


def test_free_branch_is_the_plain_date_form_when_nothing_holds_it() -> None:
    assert _free_branch([], "claude", TODAY) == "readiness/claude/2026-03-04"


def test_free_branch_is_suffixed_2_when_the_plain_form_is_taken() -> None:
    taken = [_run_with(harness="claude", branch="readiness/claude/2026-03-04")]

    assert _free_branch(taken, "claude", TODAY) == "readiness/claude/2026-03-04-2"


def test_free_branch_is_suffixed_3_when_2_is_also_taken() -> None:
    taken = [
        _run_with(harness="claude", branch="readiness/claude/2026-03-04"),
        _run_with(harness="claude", branch="readiness/claude/2026-03-04-2"),
    ]

    assert _free_branch(taken, "claude", TODAY) == "readiness/claude/2026-03-04-3"


def test_free_branch_ignores_a_run_with_no_branch_input() -> None:
    no_branch = Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="repo-init",
        template_version=1,
        inputs={"harness": "claude"},
        status="running",
        budget_usd=BUDGET,
        created_at=NOW,
    )

    assert _free_branch([no_branch], "claude", TODAY) == "readiness/claude/2026-03-04"


# ── `_readiness_repository` (pure) ───────────────────────────────────────────────────────


def test_readiness_repository_finds_the_one_slugged_readiness_repo() -> None:
    world = World()

    found = _readiness_repository(world.repositories, world.project.id)

    assert found is not None
    assert found.id == world.repository.id


def test_readiness_repository_answers_none_when_the_project_holds_no_such_slug() -> None:
    project_id = new_id()
    other = readiness_repository(project_id).model_copy(update={"slug": "something-else"})
    repositories = FakeRepositoryRepository([other])

    assert _readiness_repository(repositories, project_id) is None


# ── the Template is configuration, not a constant ─────────────────────────────────────────
# Operator decision 2026-09-30: no template name hardcoded in product code. These two
# replace the `repo_init_shape` fixture that used to monkeypatch the module constants
# `READINESS_TEMPLATE_NAME`/`_VERSION`, and assert more than it did: the *configured* name
# is what the Run pins, and the version is resolved off the store rather than written down.


def test_the_run_is_planned_from_the_configured_template() -> None:
    world = World()

    result = world.start("claude")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.template_name == TEMPLATE_NAME


def test_the_pinned_version_is_the_latest_stored_one() -> None:
    world = World()

    result = world.start("claude")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.template_version == max(world.templates.list_versions(TEMPLATE_NAME))


def test_a_configured_template_nothing_stores_is_not_found() -> None:
    world = World(template_name="no-such-template")

    with pytest.raises(NotFound, match="no-such-template"):
        world.start("claude")
