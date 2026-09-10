"""`run_preflight` (SPEC CAP-3, FR-8): the story's own acceptance criteria, over the four
shipped Templates plan_fixtures already scripts for 4.2's own tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.preflight.model import (
    CHECK_BRANCH,
    CHECK_HARNESS,
    CHECK_METHOD_VERSION,
    CHECK_STORIES_YAML,
    QUEUE_FREE,
    Line,
    PreflightRequest,
)
from orchestrator.application.templates.plan_model import CALLEE_NOT_RESOLVED, PlanError
from orchestrator.application.use_cases import preflight as preflight_uc
from orchestrator.application.use_cases.preflight import PreflightPorts, run_preflight
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WORK_DIR = Path("/work")
MANIFEST_PATH = "_bmad/_config/manifest.yaml"
#: `repo-init@1`'s row count (4.2's own AC): plan, checkout, install, commit, push, link.
#: `repo-init@1`'s own rows plus AD-7's `plan` row: seven steps since the `context`
#: dispatch and the stop after it landed.
REPO_INIT_ROW_COUNT = 8


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


def ports(*, git: FakeGit, **overrides: object) -> PreflightPorts:
    fields: dict[str, object] = {
        "git": git,
        "templates": fixtures.repository_of_versions(),
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "repositories": FakeRepositoryRepository([repository()]),
        "projects": FakeProjectRepository([project()]),
        "bmad_version": fixtures.BMAD_VERSION,
        "max_active_runs": 2,
        "work_dir": WORK_DIR,
    }
    fields.update(overrides)
    return PreflightPorts(**fields)  # type: ignore[arg-type]


def epic_request(**overrides: object) -> PreflightRequest:
    fields: dict[str, object] = {
        "template_name": "epic",
        "template_version": 1,
        "project_id": fixtures.PROJECT.id,
        "repository_id": fixtures.REPOSITORY.id,
        "base_branch": fixtures.BASE_BRANCH,
        "inputs": {"branch": fixtures.EPIC_BRANCH, "spec_folder": fixtures.SPEC_FOLDER},
    }
    fields.update(overrides)
    return PreflightRequest(**fields)  # type: ignore[arg-type]


def line(result: object, check: str) -> Line:
    found = next(candidate for candidate in result.lines if candidate.check == check)  # type: ignore[attr-defined]
    return found


# --- the brief's acceptance criteria ------------------------------------------------------------


def test_ac1_repo_init_full_success() -> None:
    req = PreflightRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
    )

    result = run_preflight(ports(git=fixtures.repo_init_git()), req)

    assert result.start_allowed is True
    assert result.rows is not None
    assert len(result.rows) == REPO_INIT_ROW_COUNT
    assert result.queue_note == QUEUE_FREE
    assert line(result, CHECK_BRANCH).text == "chore/bmad-init-1 · will create from main"
    assert line(result, CHECK_METHOD_VERSION).status == "skip"


def test_ac2_stories_yaml_ids_not_prefix_free() -> None:
    bad_stories = (
        '- id: "4-1"\n  title: A\n  description: a\n- id: "4-1-a"\n  title: B\n  description: b\n'
    )
    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, fixtures.EPIC_BRANCH: fixtures.WORK_SHA},
        files={(fixtures.WORK_SHA, f"{fixtures.SPEC_FOLDER}/stories.yaml"): bad_stories},
    )

    result = run_preflight(ports(git=git), epic_request())

    assert result.start_allowed is False
    assert result.rows is None
    assert result.plan_error is not None
    stories_line = line(result, CHECK_STORIES_YAML)
    assert stories_line.status == "fail"
    assert "4-1-a" in stories_line.text


def test_ac3_harness_disabled() -> None:
    harnesses = FakeHarnessRepository(
        [Harness(name="claude", enabled=False, version_pin="2.1.258")]
    )
    req = epic_request(harness="claude")

    result = run_preflight(ports(git=fixtures.epic_git(), harnesses=harnesses), req)

    assert line(result, CHECK_HARNESS) == Line(
        CHECK_HARNESS, "fail", "disabled: no readiness run", "re-run readiness on this screen"
    )


def test_ac4_held_branch() -> None:
    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, "feat/x": fixtures.WORK_SHA},
        files={(fixtures.WORK_SHA, f"{fixtures.SPEC_FOLDER}/stories.yaml"): fixtures.EPIC_STORIES},
    )
    holder = Run(
        id=new_id(),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="epic",
        template_version=1,
        status="running",
        inputs={},
        budget_usd=Decimal("0"),
        worktrees=(Worktree(branch="feat/x", path="/work/x", created_branch=True, pushed=False),),
        created_at=NOW,
    )
    req = epic_request(inputs={"branch": "feat/x", "spec_folder": fixtures.SPEC_FOLDER})

    result = run_preflight(ports(git=git, runs=FakeRunRepository([holder])), req)

    assert line(result, CHECK_BRANCH) == Line(
        CHECK_BRANCH, "fail", "held by run epic · feat/x", "wait for that run or cancel it"
    )
    assert result.queue_note == "queues behind epic · feat/x"


def test_method_version_outdated() -> None:
    git = fixtures.epic_git()
    git.files[(fixtures.WORK_SHA, MANIFEST_PATH)] = "installation:\n  version: 6.10.0\n"

    result = run_preflight(ports(git=git, bmad_version=fixtures.BMAD_VERSION), epic_request())

    assert line(result, CHECK_METHOD_VERSION) == Line(
        CHECK_METHOD_VERSION,
        "fail",
        "outdated: 6.10.0",
        "run Initialise repository and merge its branch",
    )


def test_ac5_missing_repository_id_every_line_skips() -> None:
    req = epic_request(repository_id=None, harness="claude")

    result = run_preflight(ports(git=fixtures.epic_git()), req)

    assert result.start_allowed is False
    assert result.rows is None
    assert all(candidate.status == "skip" for candidate in result.lines)


def test_an_initiative_request_carries_the_epics_yaml_line() -> None:
    req = PreflightRequest(
        template_name="initiative",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        inputs={"initiative_folder": fixtures.INITIATIVE_FOLDER},
    )

    result = run_preflight(ports(git=fixtures.initiative_git()), req)

    epics_line = line(result, "epics.yaml")
    assert epics_line.status == "ok"
    assert "2 epics" in epics_line.text


def test_an_entirely_empty_request_every_line_skips() -> None:
    """What the `GET /runs/preflight` sibling answers."""
    result = run_preflight(ports(git=FakeGit()), PreflightRequest())

    assert result.start_allowed is False
    assert result.rows is None
    assert result.queue_note == QUEUE_FREE
    assert result.lines
    assert all(candidate.status == "skip" for candidate in result.lines)


# --- unresolvable entities -----------------------------------------------------------------------


def test_an_unknown_project_id_is_treated_as_missing() -> None:
    req = epic_request(project_id=new_id())

    result = run_preflight(ports(git=fixtures.epic_git()), req)

    assert result.rows is None
    assert result.plan_error is None


def test_an_unknown_repository_id_is_treated_as_missing() -> None:
    req = epic_request(repository_id=new_id())

    result = run_preflight(ports(git=fixtures.epic_git()), req)

    assert result.rows is None
    assert result.plan_error is None


def test_an_unknown_template_is_a_plan_error_on_what_will_run() -> None:
    req = epic_request(template_name="no-such-template")

    result = run_preflight(ports(git=fixtures.epic_git()), req)

    assert result.plan_error is not None
    assert result.plan_error.reason == CALLEE_NOT_RESOLVED
    assert result.rows is None


# --- the private helpers, directly ----------------------------------------------------------------


def test_resolve_tree_none_when_the_request_names_none() -> None:
    tree, error = preflight_uc._resolve_tree(FakeTemplateVersionRepository(), None, None)

    assert tree is None
    assert error is None


def test_resolve_tree_error_when_the_version_is_not_stored() -> None:
    tree, error = preflight_uc._resolve_tree(FakeTemplateVersionRepository(), "no-such-template", 1)

    assert tree is None
    assert error is not None
    assert error.reason == CALLEE_NOT_RESOLVED


def test_resolve_tree_resolves_a_stored_root() -> None:
    tree, error = preflight_uc._resolve_tree(fixtures.repository_of_versions(), "repo-init", 1)

    assert error is None
    assert tree is not None
    assert tree.root.name == "repo-init"


def test_build_plan_short_circuits_on_a_tree_error() -> None:
    tree_error = PlanError(reason=CALLEE_NOT_RESOLVED, item="x@1")
    resolved = preflight_uc._Resolved(None, None, WORK_DIR, None, tree_error)

    plan, error = preflight_uc._build_plan(ports(git=FakeGit()), PreflightRequest(), resolved)

    assert plan is None
    assert error is tree_error


def test_build_plan_none_none_when_inputs_cannot_be_built() -> None:
    resolved = preflight_uc._Resolved(project(), None, WORK_DIR, fixtures.tree("repo-init"), None)

    plan, error = preflight_uc._build_plan(ports(git=FakeGit()), PreflightRequest(), resolved)

    assert plan is None
    assert error is None


def test_run_inputs_none_without_a_project() -> None:
    inputs = preflight_uc._run_inputs(PreflightRequest(base_branch="main"), None, repository())

    assert inputs is None


def test_run_inputs_none_without_a_repository() -> None:
    inputs = preflight_uc._run_inputs(PreflightRequest(base_branch="main"), project(), None)

    assert inputs is None


def test_run_inputs_none_without_a_base_branch() -> None:
    inputs = preflight_uc._run_inputs(PreflightRequest(), project(), repository())

    assert inputs is None


def test_run_inputs_full_when_every_field_resolves() -> None:
    inputs = preflight_uc._run_inputs(
        PreflightRequest(base_branch="main", harness="codex", model="m"), project(), repository()
    )

    assert inputs is not None
    assert inputs.harness == "codex"
    assert inputs.model == "m"


def test_run_inputs_defaults_the_harness_when_the_request_names_none() -> None:
    inputs = preflight_uc._run_inputs(PreflightRequest(base_branch="main"), project(), repository())

    assert inputs is not None
    assert inputs.harness == preflight_uc.DEFAULT_HARNESS


def test_base_dir_is_the_work_dir_when_either_entity_is_missing() -> None:
    assert preflight_uc._base_dir(WORK_DIR, None, repository()) == WORK_DIR
    assert preflight_uc._base_dir(WORK_DIR, project(), None) == WORK_DIR


def test_base_dir_composes_project_and_repository_slugs() -> None:
    resolved = preflight_uc._base_dir(WORK_DIR, project(), repository())

    assert resolved == WORK_DIR / fixtures.PROJECT.slug / fixtures.REPOSITORY.slug / "base"


def test_a_repository_with_no_quality_gate_command_maps_to_none() -> None:
    """`RepositorySnapshot`'s own convention: an empty command is "states none" (AD-15)."""
    no_gate = repository(quality_gate_command="")

    inputs = preflight_uc._run_inputs(PreflightRequest(base_branch="main"), project(), no_gate)

    assert inputs is not None
    assert inputs.repository.quality_gate_command is None
