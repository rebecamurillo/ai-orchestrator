"""Planning survives a git command that fails (SPEC CAP-3, FR-8).

`_build_plan` catches `PlanError` — the Template refusing to plan — but a plan also issues
git commands: `plan_ref` resolves the working branch with `ls_remote`, and a remote that is
unreachable, missing, or slow enough to time out raises `GitError` from the adapter. Until
this suite existed that exception went straight through `preflight_and_plan`,
`run_preflight` and `create_run` and out of the API as a 500.

That is the same class of failure the *lines* have always handled: `preflight/checks.py`
declares `STEP_FAILURES = (GitError, OSError)` and turns each into a `fail` line carrying
git's own redacted words. Pre-flight exists to answer "can this Run start, and if not
why" — an unreachable remote is one of the answers it is for, not a crash. So the plan half
is brought to the same rule as the line half: the failure becomes the `PlanError` that
`start_allowed` already reads, and the operator gets a problem document naming the command
instead of an empty 500.

`GitError.output` is redacted by the adapter before it is raised (AD-5), so carrying its
sentence into the `PlanError` cannot leak a credential.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.preflight.model import CHECK_ORIGIN, PreflightRequest
from orchestrator.application.use_cases.preflight import PreflightPorts, run_preflight
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ports.git import GitError
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WORK_DIR = Path("/work")

#: What `SubprocessGit._run` raises when the remote is not a repository — the exact failure
#: `POST /api/v1/harnesses/0/readiness` produced in CI, minus the paths.
UNREACHABLE = GitError(
    command="git ls-remote --heads -- file:///work/readiness/origin.git readiness/x/2026-09-08",
    exit_code=128,
    output="fatal: could not read from remote repository.",
)


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
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def failing_ports(error: Exception) -> PreflightPorts:
    """Pre-flight's own ports over a git port whose every command raises `error`."""
    return PreflightPorts(
        git=FakeGit(ls_remote=[error]),
        templates=fixtures.repository_of_versions(),
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([repository()]),
        projects=FakeProjectRepository([project()]),
        bmad_version=fixtures.BMAD_VERSION,
        max_active_runs=2,
        work_dir=WORK_DIR,
    )


def epic_request() -> PreflightRequest:
    return PreflightRequest(
        template_name="epic",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        inputs={"branch": fixtures.EPIC_BRANCH, "spec_folder": fixtures.SPEC_FOLDER},
    )


# ── the failure is answered, not raised ───────────────────────────────────────────────────


def test_a_git_failure_while_planning_is_a_plan_error_and_not_an_exception() -> None:
    result = run_preflight(failing_ports(UNREACHABLE), epic_request())

    assert result.plan_error is not None
    assert result.rows is None


def test_a_git_failure_while_planning_refuses_the_start() -> None:
    result = run_preflight(failing_ports(UNREACHABLE), epic_request())

    assert result.start_allowed is False


def test_the_plan_error_carries_gits_own_words() -> None:
    """A refusal that does not say what git said leaves the operator with nothing to act on."""
    result = run_preflight(failing_ports(UNREACHABLE), epic_request())

    assert result.plan_error is not None
    assert "could not read from remote repository" in str(result.plan_error).lower()


def test_the_origin_line_still_fails_for_the_same_reason() -> None:
    """The line half already handled this; catching it in the plan half must not silence it."""
    result = run_preflight(failing_ports(UNREACHABLE), epic_request())

    origin = next(line for line in result.lines if line.check == CHECK_ORIGIN)
    assert origin.status == "fail"


def test_an_os_error_while_planning_is_answered_the_same_way() -> None:
    """`checks.STEP_FAILURES` pairs `OSError` with `GitError` — a clone path that cannot be
    read is this instance's own failure, and it reaches planning by the same route."""
    result = run_preflight(failing_ports(OSError("no space left on device")), epic_request())

    assert result.plan_error is not None
    assert result.start_allowed is False


def test_a_reachable_remote_still_plans() -> None:
    """The guard must catch a failure, not swallow a plan: the same request over the same
    Template with a working git port still produces rows."""
    ports = PreflightPorts(
        git=fixtures.epic_git(),
        templates=fixtures.repository_of_versions(),
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([repository()]),
        projects=FakeProjectRepository([project()]),
        bmad_version=fixtures.BMAD_VERSION,
        max_active_runs=2,
        work_dir=WORK_DIR,
    )

    result = run_preflight(ports, epic_request())

    assert result.plan_error is None
    assert result.rows is not None
