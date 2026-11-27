"""`git.push` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_push import KIND, GitPushExecutor
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import (
    BRANCH,
    DEFAULT_BRANCH,
    a_context,
    a_row,
    a_worktree,
    an_environment,
    without,
)


def a_push_context(git: FakeGit, branch: str = BRANCH, resume: str | None = None, **extra: object):
    row = a_row(kind=KIND, with_resolved={"branch": branch, **extra}, path="push")
    return a_context(
        row,
        git=git,
        env=an_environment(worktrees=(a_worktree(),)),
        resume=resume,  # type: ignore[arg-type]
    )


def lines_of(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_a_push_logs_the_command_and_the_remotes_output() -> None:
    git = FakeGit(push=["To origin\nbranch feat"])
    ctx = a_push_context(git)

    result = GitPushExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    lines = lines_of(ctx)
    assert any(line.startswith("> push ") for line in lines)
    assert "  To origin" in lines and "  branch feat" in lines
    ops = [line.split()[1] for line in lines if line.startswith("> ")]
    assert ops == [call[0] for call in git.calls]


def test_a_retry_syncs_first_and_still_logs_no_refs_line() -> None:
    ctx = a_push_context(FakeGit(push=["ok"]), resume="retry")

    GitPushExecutor().execute(ctx)

    lines = lines_of(ctx)
    assert any(line.startswith("> sync ") for line in lines)
    assert not [line for line in lines if line.startswith("refs updated:")]


def test_every_outcome_carries_the_log_and_keeps_its_fields() -> None:
    rejected = GitError(command="git push", exit_code=1, output="rejected")
    cases = [
        ({"push": [rejected]}, BRANCH, None, {}),
        ({}, DEFAULT_BRANCH, None, {}),
        ({"sync": [rejected]}, BRANCH, "retry", {}),
        ({"push": ["ok"]}, BRANCH, None, {"workdir": "repos/member"}),
        ({"push": [None]}, BRANCH, None, {"workdir": "repos/member"}),
    ]
    for script, branch, resume, extra in cases:
        ctx = a_push_context(FakeGit(**script), branch, resume, **extra)  # type: ignore[arg-type]
        bare = without(a_push_context(FakeGit(**script), branch, resume, **extra), step_log=None)  # type: ignore[arg-type]

        result = GitPushExecutor().execute(ctx)
        plain = GitPushExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
