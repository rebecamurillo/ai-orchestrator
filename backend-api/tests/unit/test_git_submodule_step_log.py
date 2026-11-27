"""`git.submodule` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_submodule import KIND, GitSubmoduleExecutor
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import a_context, a_row, without


def a_submodule_context(git: FakeGit, **resolved: object) -> StepContext:
    return a_context(
        a_row(kind=KIND, with_resolved={"timeout_min": 10, **resolved}, path="submodules"), git=git
    )


def test_an_update_logs_each_git_call_with_its_answer_lines() -> None:
    git = FakeGit(submodule_update=[("repos/a", "repos/b")])
    ctx = a_submodule_context(git)

    result = GitSubmoduleExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    writes = ctx.ports.step_log.writes  # type: ignore[union-attr]
    assert len(writes) == 1
    lines = writes[0][3]
    assert lines[0].startswith("> submodule_update ")
    assert "  repos/a" in lines and "  repos/b" in lines
    assert not [line for line in lines if line.startswith("refs updated:")]


def test_an_ambiguous_form_makes_no_git_call_and_logs_an_empty_file() -> None:
    git = FakeGit()
    ctx = a_submodule_context(git, update=True, workdir="repos/a")

    result = GitSubmoduleExecutor().execute(ctx)

    assert result.park is not None
    assert git.calls == []
    assert result.log_path == str(log_path(ctx))
    assert ctx.ports.step_log.writes[0][3] == ()  # type: ignore[union-attr]


def test_every_outcome_carries_the_log_and_keeps_its_fields() -> None:
    failed = GitError(command="git submodule", exit_code=1, output="denied")
    cases = [
        ({"submodule_update": [("a",)]}, {}),
        ({"submodule_update": [failed]}, {}),
        ({"submodule_checkout": [None]}, {"workdir": "repos/a", "branch": "b"}),
        ({}, {"workdir": "repos/a"}),
    ]
    for script, resolved in cases:
        ctx = a_submodule_context(FakeGit(**script), **resolved)  # type: ignore[arg-type]
        bare = without(a_submodule_context(FakeGit(**script), **resolved), step_log=None)  # type: ignore[arg-type]

        result = GitSubmoduleExecutor().execute(ctx)
        plain = GitSubmoduleExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
