"""`git.commit` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_commit import KIND, GitCommitExecutor
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import WORKTREE, a_context, a_row, an_environment, without

DIRTY = " M src/thing.py\n"


def a_commit_context(git: FakeGit, **resolved: object) -> StepContext:
    row = a_row(kind=KIND, with_resolved={"message": "m", **resolved}, path="commit")
    return a_context(row, git=git, env=an_environment())


def lines_of(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_a_commit_logs_each_call_in_order_and_names_the_path() -> None:
    git = FakeGit(status=[DIRTY])
    ctx = a_commit_context(git)

    result = GitCommitExecutor().execute(ctx)

    assert result.status == "done"
    assert result.log_path == str(log_path(ctx))
    assert len(ctx.ports.step_log.writes) == 1  # type: ignore[union-attr]
    ops = [line.split()[1] for line in lines_of(ctx) if line.startswith("> ")]
    assert ops == [call[0] for call in git.calls]
    assert not [line for line in lines_of(ctx) if line.startswith("refs updated:")]


def test_a_stage_that_answers_none_has_no_answer_line() -> None:
    ctx = a_commit_context(FakeGit(status=[DIRTY], stage=[None]))

    GitCommitExecutor().execute(ctx)

    lines = lines_of(ctx)
    assert lines[0] == f"> stage {WORKTREE}"
    assert lines[1].startswith("> status ")


def test_every_outcome_carries_the_log_and_keeps_its_fields() -> None:
    failed = GitError(command="git add", exit_code=1, output="locked")
    scripts = [
        {"status": [""]},
        {"status": [DIRTY]},
        {"stage": [failed]},
        {"status": [DIRTY], "commit": [failed]},
    ]
    for script in scripts:
        ctx = a_commit_context(FakeGit(**script))  # type: ignore[arg-type]
        bare = without(a_commit_context(FakeGit(**script)), step_log=None)  # type: ignore[arg-type]

        result = GitCommitExecutor().execute(ctx)
        plain = GitCommitExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})


def test_a_workdir_commit_logs_through_the_recorder_too() -> None:
    git = FakeGit(status=[DIRTY])
    ctx = a_commit_context(git, workdir="repos/member")

    result = GitCommitExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    ops = [line.split()[1] for line in lines_of(ctx) if line.startswith("> ")]
    assert ops == [call[0] for call in git.calls]
