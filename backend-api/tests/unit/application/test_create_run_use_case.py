"""`create_run` (SPEC CAP-4, FR-6, FR-8): persist a plan, then enqueue it (AD-7).

Every scenario reuses the shipped-Template fixtures `tests/unit/application/templates/
plan_fixtures.py` already builds for the planner (4.2) and pre-flight (4.3): `create_run`
is meant to plan from the exact same pure functions, so a second, hand-rolled tree would
prove nothing this suite could not already prove by reusing the first one.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import Worktree
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
REPO_INIT_ROW_COUNT = 8
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
    """One set of fakes, wired the way `api/providers.py::create_run_ports` wires them."""

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
        """Enter the unit of work the way `api/providers.py::create_run_ports` does —
        a FastAPI dependency opens it before the use case ever runs."""
        with self.uow:
            return create_run(self.ports, request)


# ── AC1: a passing pre-flight for repo-init@1 ────────────────────────────────────────────


def test_repo_init_persists_eight_rows_pins_one_version_and_enqueues_once() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request())

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.pinned_versions == (fixtures.TemplateRef(name="repo-init", version=1),)
    rows = harness.steps.list_for_run(result.run.id)
    assert len(rows) == REPO_INIT_ROW_COUNT
    assert [row.seq for row in rows] == list(range(1, REPO_INIT_ROW_COUNT + 1))
    assert rows[0].path == "plan"
    assert all(row.status == "planned" for row in rows)
    # operator revision 2026-09-15: partition by (repository, branch)
    assert harness.engine.calls == [
        ("enqueue", (result.run.id, f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"))
    ]
    assert result.starts_now is True


def initiative_git_with_a_passing_preflight() -> FakeGit:
    """`fixtures.initiative_git()`, plus what `create_run` also re-runs pre-flight over:
    each epic's `SPEC.md` (line 7), which the planner itself does not need, so the planner's
    own fixture omits them.

    The `SPEC.md` paths sit under the Initiative folder: `epics.yaml` declares each
    `spec_folder` relative to it (PRD §3 "Initiative"), and line 7 reads the composed
    path. They were bare (`epic-1/SPEC.md`) while pre-flight read them verbatim —
    revised with that defect's fix (Operator ruling, 2026-09-16; hard rule 1 case (c))."""
    git = fixtures.initiative_git()
    git.files = {
        **(git.files or {}),
        (fixtures.BASE_SHA, f"{fixtures.INITIATIVE_FOLDER}/epic-1/SPEC.md"): "# spec",
        (fixtures.BASE_SHA, f"{fixtures.INITIATIVE_FOLDER}/epic-2/SPEC.md"): "# spec",
    }
    return git


# ── AC2: initiative@1 pins the whole call tree, and `pinned_by` counts it ───────────────


def test_initiative_pins_the_whole_tree_and_pinned_by_counts_each_version() -> None:
    harness = Harness(git=initiative_git_with_a_passing_preflight())
    request = base_request(
        template_name="initiative",
        inputs={"initiative_folder": fixtures.INITIATIVE_FOLDER},
    )

    result = harness.create(request)

    assert result.run.pinned_versions == (
        fixtures.TemplateRef(name="initiative", version=1),
        fixtures.TemplateRef(name="epic", version=1),
        fixtures.TemplateRef(name="story", version=1),
    )
    assert harness.templates.pinned_by("story", 1) == 1
    assert harness.templates.pinned_by("epic", 1) == 1
    assert harness.templates.pinned_by("initiative", 1) == 1
    assert harness.templates.pinned_by("repo-init", 1) == 0


# ── AC3: a non-terminal Run already holds the Repository ───────────────────────────────


def test_a_second_run_against_a_held_repository_still_creates_but_waits() -> None:
    holder = Run(
        id=UUID("01960000-0000-7000-9000-000000000099"),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=BUDGET,
        inputs={"base_branch": fixtures.BASE_BRANCH},
        created_at=NOW,
    )
    harness = Harness(git=fixtures.repo_init_git(), existing=[holder])

    result = harness.create(base_request())

    assert result.starts_now is False
    assert result.waiting == f"queues behind repo-init · {fixtures.BASE_BRANCH}"
    assert harness.runs.get(result.run.id) is not None
    assert result.run.status == "queued"


# ── AC4: a failing pre-flight line refuses with a 409-shaped `Conflict` ─────────────────


def test_a_failing_line_is_a_conflict_and_writes_no_run() -> None:
    # a non-terminal Run already holding the branch `repo-init@1` would create fails line 3
    # (`branch`) without touching `plan_ref` at all — the base branch still resolves fine,
    # so this is the fail-line path and not the `PlanError` one (AC5 below).
    # operator revision 2026-09-15: partition by (repository, branch) — holder needs
    # partition_branch set so _holding_run detects it; worktrees alone no longer trigger the check.
    # Revised: a saved Run holds no branch (multi-repo initiative S2, spine AD-14
    # amendment, 2026-09-23) — `engine_ref` set so the holder is in the engine, which is
    # exactly the case that still refuses.
    holder = Run(
        id=UUID("01960000-0000-7000-9000-0000000000cc"),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=BUDGET,
        partition_branch=fixtures.INIT_BRANCH,
        engine_ref={"ref": 1},
        worktrees=(
            Worktree(
                branch=fixtures.INIT_BRANCH, path="/work/x", created_branch=True, pushed=False
            ),
        ),
        created_at=NOW,
    )
    harness = Harness(git=fixtures.repo_init_git(), existing=[holder])

    with pytest.raises(Conflict) as excinfo:
        harness.create(base_request())

    assert "held by run" in str(excinfo.value)
    assert harness.runs.runs == {holder.id: holder}
    assert harness.engine.calls == []


# ── AC5: an unbuildable plan is the `PlanError` itself (422 at the router) ──────────────


def test_a_plan_error_is_raised_and_writes_no_run() -> None:
    harness = Harness(git=fixtures.initiative_git())
    # `initiative` reads `epics.yaml` from the base commit; scripting no files at all makes
    # `plan_run` raise `LIST_FILE_NOT_FOUND` for it (4.2's own rule)
    empty_git = FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files={}, listings={})
    harness = Harness(git=empty_git)
    request = base_request(
        template_name="initiative", inputs={"initiative_folder": fixtures.INITIATIVE_FOLDER}
    )

    with pytest.raises(PlanError):
        harness.create(request)

    assert harness.runs.runs == {}
    assert harness.engine.calls == []


# ── AC6: the step-row insert fails ──────────────────────────────────────────────────────


def test_when_the_step_insert_raises_nothing_commits_and_enqueue_is_not_called() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    def _raise(steps: object) -> None:
        raise RuntimeError("boom")

    harness.steps.add_many = _raise  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        harness.create(base_request())

    assert harness.uow.committed is False
    assert harness.uow.rolled_back is True
    assert harness.engine.calls == []


# ── unresolvable Project / Repository ────────────────────────────────────────────────────


def test_an_unknown_project_is_not_found() -> None:
    harness = Harness(git=fixtures.repo_init_git())
    request = base_request(project_id=UUID("01960000-0000-7000-9000-0000000000aa"))

    with pytest.raises(NotFound):
        harness.create(request)


def test_an_unknown_repository_is_not_found() -> None:
    harness = Harness(git=fixtures.repo_init_git())
    request = base_request(repository_id=UUID("01960000-0000-7000-9000-0000000000bb"))

    with pytest.raises(NotFound):
        harness.create(request)


# ── skip_harness_check (AD-10) ───────────────────────────────────────────────────────────


def test_skip_harness_check_looks_past_a_failing_harness_line_only() -> None:
    """`epic@1` has no `agent` step either, so this proves the flag is inert here — the
    real effect (a `readiness` Run) is Epic 5's; 4.4 only has to accept the flag."""
    harness = Harness(git=fixtures.repo_init_git())
    harness.ports = replace(harness.ports, skip_harness_check=True)

    result = harness.create(base_request())

    assert result.run.status == "queued"


# ── manual_estimate_h and budget_usd are stored, not re-derived ──────────────────────────


def test_budget_and_manual_estimate_are_stored_on_the_run() -> None:
    harness = Harness(git=fixtures.repo_init_git())
    request = base_request(budget_usd=Decimal("42.5"), manual_estimate_h=Decimal("3.5"))

    result = harness.create(request)

    assert result.run.budget_usd == Decimal("42.5")
    assert result.run.manual_estimate_h == Decimal("3.5")
    assert result.run.re_review_done is False


def test_the_engine_ref_is_written_back_after_enqueue() -> None:
    harness = Harness(git=fixtures.repo_init_git())

    result = harness.create(base_request())

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.engine_ref == {"ref": 1}


def test_active_runs_at_the_concurrency_cap_queue_by_global_concurrency() -> None:
    active = [
        Run(
            id=UUID(f"01960000-0000-7000-9000-0000000000{n:02d}"),
            project_id=fixtures.PROJECT.id,
            repository_id=UUID("01960000-0000-7000-9000-000000000fff"),
            template_name="repo-init",
            template_version=1,
            status="running",
            budget_usd=BUDGET,
            created_at=NOW,
        )
        for n in range(1, 3)
    ]
    harness = Harness(git=fixtures.repo_init_git(), existing=active)

    result = harness.create(base_request())

    assert result.starts_now is False
    assert "global concurrency" in result.waiting
    assert result.run.status not in TERMINAL_RUN
