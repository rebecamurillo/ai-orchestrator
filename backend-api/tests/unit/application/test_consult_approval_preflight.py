"""Pre-flight warns when the repository freezes no test (story 1-5, spine AD-17, 2026-11-02):
with `test_globs` empty, no existing test is an anchor, so a senior's approval and AD-17's
check have nothing to protect. A warning never refuses a start."""

from __future__ import annotations

from orchestrator.application.preflight import lists
from orchestrator.application.preflight.model import (
    CHECK_CLONE_CHECK,
    CHECK_TEST_GLOBS,
    Line,
    PreflightRequest,
)
from orchestrator.application.use_cases.preflight import run_preflight
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_use_case import ports, repository
from tests.unit.fakes.projects import FakeRepositoryRepository
from tests.unit.test_preflight_installed_skill import _ctx

WARNING = Line(check="test globs", status="warn", text="no test_globs: no existing test is frozen")


def test_an_empty_glob_list_warns() -> None:
    assert lists.test_globs_line(_ctx(repository=repository(test_globs=()))) == WARNING


def test_a_glob_list_says_nothing() -> None:
    assert lists.test_globs_line(_ctx(repository=repository(test_globs=("tests/**",)))) is None


def test_no_repository_chosen_says_nothing() -> None:
    assert lists.test_globs_line(_ctx(repository=None)) is None


def a_preflight(test_globs: tuple[str, ...]) -> list[Line]:
    req = PreflightRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
    )
    chosen = FakeRepositoryRepository([repository(test_globs=test_globs)])
    result = run_preflight(ports(git=fixtures.repo_init_git(), repositories=chosen), req)
    assert result.start_allowed is True
    return list(result.lines)


def test_the_warning_follows_the_clone_check_and_the_start_stays_allowed() -> None:
    checks = [line.check for line in a_preflight(())]

    assert CHECK_TEST_GLOBS == "test globs"
    assert checks[checks.index(CHECK_CLONE_CHECK) + 1] == CHECK_TEST_GLOBS
    assert checks.count(CHECK_TEST_GLOBS) == 1


def test_a_repository_with_globs_gets_no_line() -> None:
    assert CHECK_TEST_GLOBS not in [line.check for line in a_preflight(("tests/**",))]
