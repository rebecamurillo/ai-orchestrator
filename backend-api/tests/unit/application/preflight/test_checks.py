"""The pre-flight line-builders that need no list file (FR-8, lines 1-3, 6, 8, 9, 11, 12)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.preflight import checks
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import (
    CHECK_BASE_BRANCH,
    CHECK_BRANCH,
    CHECK_CHECKPOINTS,
    CHECK_CLONE_CHECK,
    CHECK_EPICS_YAML,
    CHECK_HARNESS,
    CHECK_METHOD_VERSION,
    CHECK_ORIGIN,
    CHECK_STORIES_YAML,
    CHECK_WHAT_WILL_RUN,
    QUEUE_FREE,
    Line,
    PreflightRequest,
)
from orchestrator.application.templates.plan_model import (
    DUPLICATE_ROW_PATH,
    ID_NOT_PREFIX_FREE,
    Plan,
    PlanError,
)
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError, RemoteRef
from orchestrator.domain.values import PlannedRow, Worktree
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
URL = "https://example.test/org/my-repo.git"


def repo(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "slug": "my-repo",
        "url": URL,
        "default_branch": "main",
        "install_command": "uv sync",
        "quality_gate_command": "make check",
        "unit_test_command": "pytest -q",
        "test_globs": ("tests/**",),
        "package_manager": "uv",
        "clone_check": CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


def run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "inputs": {},
        "budget_usd": Decimal("0"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def row(**overrides: object) -> PlannedRow:
    fields: dict[str, object] = {
        "seq": 1,
        "path": "checkout",
        "label": "checkout",
        "kind": "git.worktree",
        "gate": "deterministic",
        "status": "planned",
        "reason": None,
        "with_resolved": {},
        "frame": None,
        "story_id": None,
    }
    fields.update(overrides)
    return PlannedRow(**fields)  # type: ignore[arg-type]


def ctx(**overrides: object) -> Context:
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/my-project/my-repo/base"),
        "bmad_version": "6.11.0",
        "max_active_runs": 2,
        "repository": None,
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
    }
    fields.update(overrides)
    return Context(**fields)  # type: ignore[arg-type]


# --- line 1: origin reachable ----------------------------------------------------------------


def test_origin_reachable_skips_without_a_repository() -> None:
    line = checks.origin_reachable(ctx())

    assert line == Line(CHECK_ORIGIN, "skip", "no repository", None)


def test_origin_reachable_ok_when_ls_remote_answers() -> None:
    line = checks.origin_reachable(
        ctx(repository=repo(), git=FakeGit(ls_remote=[RemoteRef("HEAD", "deadbeef")]))
    )

    assert line.status == "ok"
    assert "deadbeef" in line.text


def test_origin_reachable_fails_when_ls_remote_answers_no_ref() -> None:
    line = checks.origin_reachable(ctx(repository=repo(), git=FakeGit(ls_remote=[None])))

    assert line.status == "fail"
    assert line.fix == "check the URL and the instance token"


def test_origin_reachable_fails_on_a_git_error() -> None:
    error = GitError(command="ls-remote", exit_code=128, output="boom")
    line = checks.origin_reachable(ctx(repository=repo(), git=FakeGit(ls_remote=[error])))

    assert line.status == "fail"
    assert line.text == "boom"


def test_origin_reachable_fails_on_an_environment_error() -> None:
    """`_reason`'s non-`GitError` branch — an unwritable work directory, `git` off `PATH`."""
    error = OSError("no such file or directory")
    line = checks.origin_reachable(ctx(repository=repo(), git=FakeGit(ls_remote=[error])))

    assert line.status == "fail"
    assert line.text == "OSError: no such file or directory"


# --- line 2: base branch -----------------------------------------------------------------------


def test_base_branch_skips_without_a_repository() -> None:
    line = checks.base_branch_line(ctx(req=PreflightRequest(base_branch="main")))

    assert line.status == "skip"


def test_base_branch_skips_without_a_base_branch() -> None:
    line = checks.base_branch_line(ctx(repository=repo()))

    assert line.status == "skip"


def test_base_branch_ok_when_it_exists() -> None:
    line = checks.base_branch_line(
        ctx(
            repository=repo(),
            req=PreflightRequest(base_branch="main"),
            git=FakeGit(refs={"main": "abc123"}),
        )
    )

    assert line == Line(CHECK_BASE_BRANCH, "ok", "main at abc123", None)


def test_base_branch_fails_without_a_fix_when_it_does_not_exist() -> None:
    line = checks.base_branch_line(
        ctx(repository=repo(), req=PreflightRequest(base_branch="main"), git=FakeGit(refs={}))
    )

    assert line == Line(CHECK_BASE_BRANCH, "fail", "branch does not exist on origin", None)


def test_base_branch_fails_on_a_git_error() -> None:
    error = GitError(command="ls-remote", exit_code=128, output="boom")
    line = checks.base_branch_line(
        ctx(
            repository=repo(),
            req=PreflightRequest(base_branch="main"),
            git=FakeGit(ls_remote=[error]),
        )
    )

    assert line.status == "fail"
    assert line.text == "boom"


# --- plan_branches ------------------------------------------------------------------------------


def test_plan_branches_is_empty_without_a_plan() -> None:
    assert checks.plan_branches(None) == ()


def test_plan_branches_dedups_and_ignores_non_worktree_rows() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(
            row(seq=1, kind="git.worktree", with_resolved={"branch": "feat/x"}),
            row(seq=2, kind="shell", with_resolved={"branch": "ignored"}),
            row(seq=3, kind="git.worktree", with_resolved={"branch": "feat/x"}),
            row(seq=4, kind="git.worktree", with_resolved={}),
        ),
    )

    assert checks.plan_branches(plan) == ("feat/x",)


# --- line 3: branch -----------------------------------------------------------------------------


def test_branch_lines_skip_one_line_when_the_plan_error_blocks_it() -> None:
    lines = checks.branch_lines(
        ctx(
            repository=repo(),
            req=PreflightRequest(base_branch="main"),
            plan_error=PlanError(reason=ID_NOT_PREFIX_FREE),
        )
    )

    assert [line.check for line in lines] == [CHECK_BRANCH]
    assert lines[0].status == "skip"


def test_branch_lines_skip_without_a_repository() -> None:
    lines = checks.branch_lines(ctx())

    assert lines[0].status == "skip"
    assert lines[0].text == "no repository or base_branch"


def test_branch_lines_skip_without_a_base_branch() -> None:
    lines = checks.branch_lines(ctx(repository=repo()))

    assert lines[0].status == "skip"


def test_branch_lines_is_empty_when_nothing_blocks_and_no_plan_exists() -> None:
    """An unreachable-in-the-full-pipeline corner: no plan, no error, but nothing missing —
    branch_lines has nothing to say and adds no line, leaving line 3 absent."""
    lines = checks.branch_lines(ctx(repository=repo(), req=PreflightRequest(base_branch="main")))

    assert lines == []


def test_branch_lines_ok_will_check_out() -> None:
    plan = Plan(plan_ref="sha", rows=(row(with_resolved={"branch": "feat/x"}),))
    lines = checks.branch_lines(
        ctx(repository=repo(), plan=plan, git=FakeGit(refs={"feat/x": "sha2"}))
    )

    assert lines == [Line(CHECK_BRANCH, "ok", "feat/x · will check out", None)]


def test_branch_lines_ok_will_create_from_base() -> None:
    plan = Plan(plan_ref="sha", rows=(row(with_resolved={"branch": "feat/x"}),))
    lines = checks.branch_lines(
        ctx(
            repository=repo(),
            plan=plan,
            req=PreflightRequest(base_branch="main"),
            git=FakeGit(refs={}),
        )
    )

    assert lines == [Line(CHECK_BRANCH, "ok", "feat/x · will create from main", None)]


def test_branch_lines_fails_when_held_by_a_non_terminal_run() -> None:
    holder = run(
        template_name="epic",
        worktrees=(Worktree(branch="feat/x", path="/work/x", created_branch=True, pushed=False),),
    )
    plan = Plan(plan_ref="sha", rows=(row(with_resolved={"branch": "feat/x"}),))
    repository = repo()
    lines = checks.branch_lines(
        ctx(
            repository=repository,
            plan=plan,
            runs=FakeRunRepository([holder.model_copy(update={"repository_id": repository.id})]),
        )
    )

    assert lines == [
        Line(CHECK_BRANCH, "fail", "held by run epic · feat/x", "wait for that run or cancel it")
    ]


def test_holding_run_none_without_a_repository() -> None:
    assert checks._holding_run(FakeRunRepository(), None, "feat/x") is None


def test_holding_run_none_when_no_non_terminal_run_holds_the_branch() -> None:
    repository = repo()
    other = run(
        template_name="epic",
        repository_id=repository.id,
        worktrees=(Worktree(branch="other", path="p", created_branch=True, pushed=False),),
    )

    assert checks._holding_run(FakeRunRepository([other]), repository, "feat/x") is None


def test_branch_lines_fails_on_a_git_error_checking_existence() -> None:
    error = GitError(command="ls-remote", exit_code=128, output="boom")
    plan = Plan(plan_ref="sha", rows=(row(with_resolved={"branch": "feat/x"}),))
    lines = checks.branch_lines(ctx(repository=repo(), plan=plan, git=FakeGit(ls_remote=[error])))

    assert lines[0].status == "fail"
    assert lines[0].text == "boom"


# --- run_label -----------------------------------------------------------------------------------


def test_run_label_prefers_the_first_worktree_branch() -> None:
    holder = run(
        template_name="epic",
        inputs={"branch": "ignored"},
        worktrees=(Worktree(branch="feat/x", path="p", created_branch=True, pushed=False),),
    )

    assert checks.run_label(holder) == "epic · feat/x"


def test_run_label_falls_back_to_inputs_branch() -> None:
    holder = run(template_name="epic", inputs={"branch": "feat/y"})

    assert checks.run_label(holder) == "epic · feat/y"


def test_run_label_falls_back_to_inputs_base_branch() -> None:
    holder = run(template_name="repo-init", inputs={"base_branch": "main"})

    assert checks.run_label(holder) == "repo-init · main"


def test_run_label_falls_back_to_empty_string() -> None:
    holder = run(template_name="repo-init", inputs={})

    assert checks.run_label(holder) == "repo-init · "


# --- queue_note ------------------------------------------------------------------------------


def test_queue_note_free_without_a_repository() -> None:
    assert checks.queue_note(ctx()) == QUEUE_FREE


def test_queue_note_names_the_holding_run() -> None:
    repository = repo()
    holder = run(
        template_name="epic",
        repository_id=repository.id,
        worktrees=(Worktree(branch="feat/x", path="p", created_branch=True, pushed=False),),
    )

    note = checks.queue_note(ctx(repository=repository, runs=FakeRunRepository([holder])))

    assert note == "queues behind epic · feat/x"


def test_queue_note_free_below_the_global_cap() -> None:
    repository = repo()

    note = checks.queue_note(ctx(repository=repository, max_active_runs=2))

    assert note == QUEUE_FREE


def test_queue_note_global_concurrency_at_the_cap() -> None:
    repository = repo()
    active = [
        run(template_name="epic", status="running", inputs={"branch": "a"}),
        run(template_name="story", status="needs_you", inputs={"branch": "b"}),
    ]
    note = checks.queue_note(
        ctx(repository=repository, runs=FakeRunRepository(active), max_active_runs=2)
    )

    assert note == "queues: global concurrency, held by epic · a, story · b"


# --- line 8: harness -----------------------------------------------------------------------------


def test_harness_skips_without_a_request_name() -> None:
    assert checks.harness_line(ctx()).status == "skip"


def test_harness_skips_without_a_repository() -> None:
    line = checks.harness_line(
        ctx(req=PreflightRequest(harness="claude"), tree=fixtures.tree("epic"))
    )

    assert line.status == "skip"
    assert line.text == "no repository"


def test_harness_skips_when_the_tree_has_no_agent_step() -> None:
    line = checks.harness_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=fixtures.tree("repo-init"),
        )
    )

    assert line == Line(CHECK_HARNESS, "skip", "no agent step", None)


def test_harness_fails_when_unknown() -> None:
    line = checks.harness_line(
        ctx(req=PreflightRequest(harness="claude"), repository=repo(), tree=fixtures.tree("epic"))
    )

    assert line == Line(
        CHECK_HARNESS, "fail", "disabled: no readiness run", "re-run readiness on this screen"
    )


def test_harness_fails_with_its_own_failing_check() -> None:
    harnesses = FakeHarnessRepository(
        [Harness(name="claude", enabled=False, failing_check="timeout", version_pin="2.1.258")]
    )
    line = checks.harness_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=fixtures.tree("epic"),
            harnesses=harnesses,
        )
    )

    assert line.text == "disabled: timeout"


def test_harness_ok_when_enabled() -> None:
    harnesses = FakeHarnessRepository([Harness(name="claude", enabled=True, version_pin="2.1.258")])
    line = checks.harness_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=fixtures.tree("epic"),
            harnesses=harnesses,
        )
    )

    assert line == Line(CHECK_HARNESS, "ok", "enabled", None)


# --- line 6: checkpoints -----------------------------------------------------------------------


def test_checkpoints_skips_without_a_plan() -> None:
    assert checks.checkpoints_line(ctx()).status == "skip"


def test_checkpoints_ok_none_declared() -> None:
    plan = Plan(plan_ref="sha", rows=(row(kind="shell"),))

    assert checks.checkpoints_line(ctx(plan=plan)) == Line(
        CHECK_CHECKPOINTS, "ok", "none declared", None
    )


def test_checkpoints_warns_a_story_done_checkpoint() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(row(kind="checkpoint", label="story 2 · done checkpoint", story_id="2"),),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).text == "story 2 · done checkpoint"


def test_checkpoints_warns_an_epic_done_checkpoint_using_the_row_label() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(row(kind="checkpoint", label="epic 1 · done checkpoint", story_id=None),),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).text == "epic 1 · done checkpoint"


def test_checkpoints_ignores_a_before_checkpoint() -> None:
    plan = Plan(
        plan_ref="sha", rows=(row(kind="checkpoint", label="story 1 · before", story_id="1"),)
    )

    assert checks.checkpoints_line(ctx(plan=plan)).status == "ok"


def test_checkpoints_warns_a_spec_checkpoint() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(row(kind="agent", story_id="3", with_resolved={"spec_checkpoint": True}),),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).text == "story 3 · spec checkpoint"


def test_checkpoints_ignores_an_agent_row_without_the_flag() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(row(kind="agent", story_id="3", with_resolved={"spec_checkpoint": False}),),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).status == "ok"


def test_checkpoints_ignores_an_agent_row_without_a_story_id() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(row(kind="agent", story_id=None, with_resolved={"spec_checkpoint": True}),),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).status == "ok"


def test_checkpoints_combines_more_than_one() -> None:
    plan = Plan(
        plan_ref="sha",
        rows=(
            row(seq=1, kind="checkpoint", label="story 1 · done checkpoint", story_id="1"),
            row(seq=2, kind="agent", story_id="2", with_resolved={"spec_checkpoint": True}),
        ),
    )

    assert checks.checkpoints_line(ctx(plan=plan)).text == (
        "story 1 · done checkpoint; story 2 · spec checkpoint"
    )


# --- line 9: method version ---------------------------------------------------------------------

MANIFEST_PATH = "_bmad/_config/manifest.yaml"


def test_method_version_skips_without_a_plan() -> None:
    assert checks.method_version_line(ctx()).status == "skip"


def test_method_version_skips_when_the_plan_installs_the_method() -> None:
    plan = Plan(plan_ref="sha", rows=(row(kind="bmad.install"),))

    assert checks.method_version_line(ctx(plan=plan)) == Line(
        CHECK_METHOD_VERSION,
        "skip",
        "plan installs the method",
        None,
    )


def test_method_version_fails_missing_when_no_manifest() -> None:
    plan = Plan(plan_ref="sha", rows=())
    line = checks.method_version_line(ctx(plan=plan, git=FakeGit(read_file=[None])))

    assert line == Line(
        CHECK_METHOD_VERSION,
        "fail",
        "missing",
        "run Initialise repository and merge its branch",
    )


def test_method_version_fails_missing_when_the_manifest_states_none() -> None:
    plan = Plan(plan_ref="sha", rows=())
    line = checks.method_version_line(
        ctx(plan=plan, git=FakeGit(read_file=["no installation section here\n"]))
    )

    assert line.text == "missing"


def test_method_version_fails_outdated() -> None:
    plan = Plan(plan_ref="sha", rows=())
    manifest = "installation:\n  version: 6.10.0\n"
    line = checks.method_version_line(
        ctx(plan=plan, bmad_version="6.11.0", git=FakeGit(read_file=[manifest]))
    )

    assert line.status == "fail"
    assert line.text == "outdated: 6.10.0"


def test_method_version_ok() -> None:
    plan = Plan(plan_ref="sha", rows=())
    manifest = "installation:\n  version: 6.11.0\n"
    line = checks.method_version_line(
        ctx(plan=plan, bmad_version="6.11.0", git=FakeGit(read_file=[manifest]))
    )

    assert line == Line(CHECK_METHOD_VERSION, "ok", "6.11.0", None)


# --- line 11: clone check ------------------------------------------------------------------------


def test_clone_check_skips_without_a_repository() -> None:
    assert checks.clone_check_line(ctx()).status == "skip"


def test_clone_check_ok() -> None:
    line = checks.clone_check_line(ctx(repository=repo()))

    assert line == Line(CHECK_CLONE_CHECK, "ok", "ok", None)


def test_clone_check_pending() -> None:
    repository = repo(clone_check=CloneCheck.pending())
    line = checks.clone_check_line(ctx(repository=repository))

    assert line == Line(CHECK_CLONE_CHECK, "fail", "pending · save the project", None)


def test_clone_check_failed() -> None:
    repository = repo(
        clone_check=CloneCheck(status="failed", at=NOW, output="boom", bmad_version=None)
    )
    line = checks.clone_check_line(ctx(repository=repository))

    assert line == Line(
        CHECK_CLONE_CHECK, "fail", "failed", "re-run the clone check on the project"
    )


# --- line 12: what will run ----------------------------------------------------------------------


def test_what_will_run_ok() -> None:
    plan = Plan(plan_ref="sha", rows=(row(), row(seq=2, path="install")))

    assert checks.what_will_run_line(ctx(plan=plan)) == Line(
        CHECK_WHAT_WILL_RUN, "ok", "2 rows", None
    )


def test_what_will_run_fails_with_the_plan_error() -> None:
    error = PlanError(reason=DUPLICATE_ROW_PATH, item="plan")
    line = checks.what_will_run_line(ctx(plan_error=error))

    assert line.status == "fail"
    assert line.text == str(error)


def test_what_will_run_skips_when_nothing_was_attempted() -> None:
    assert checks.what_will_run_line(ctx()) == Line(
        CHECK_WHAT_WILL_RUN,
        "skip",
        "missing required fields",
        None,
    )


# --- list_error_target ----------------------------------------------------------------------------


def test_list_error_target_none_without_an_error() -> None:
    assert checks.list_error_target(ctx()) is None


def test_list_error_target_none_for_an_unrelated_reason() -> None:
    error = PlanError(reason=DUPLICATE_ROW_PATH, item="plan")

    assert checks.list_error_target(ctx(plan_error=error)) is None


def test_list_error_target_stories_yaml_for_a_non_initiative_tree() -> None:
    error = PlanError(reason=ID_NOT_PREFIX_FREE, item="4-1-a")

    assert (
        checks.list_error_target(ctx(plan_error=error, tree=fixtures.tree("epic")))
        == CHECK_STORIES_YAML
    )


def test_list_error_target_epics_yaml_for_an_initiative_tree() -> None:
    error = PlanError(reason=ID_NOT_PREFIX_FREE, item="e1-a")

    assert (
        checks.list_error_target(ctx(plan_error=error, tree=fixtures.tree("initiative")))
        == CHECK_EPICS_YAML
    )


# --- Context.is_initiative ---------------------------------------------------------------------


def test_is_initiative_false_without_a_tree() -> None:
    assert ctx().is_initiative is False


def test_is_initiative_false_for_epic() -> None:
    assert ctx(tree=fixtures.tree("epic")).is_initiative is False


def test_is_initiative_true_for_initiative() -> None:
    assert ctx(tree=fixtures.tree("initiative")).is_initiative is True
