"""A hub Run's repositories are recorded as its rows run, and a push sets `head_pushed`.

Story 2 (epic 2), AC1, AC2 and AC7: the Run's own row from `create_run`, one row per workdir
from its first executor, and executor results that do not depend on recording.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.steps.context import StepContext
from orchestrator.application.steps.git_commit import GitCommitExecutor
from orchestrator.application.steps.git_push import GitPushExecutor
from orchestrator.application.steps.git_submodule import GitSubmoduleExecutor
from orchestrator.application.use_cases.create_run import create_run
from orchestrator.application.use_cases.run_records import record_own_repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.git import GitError, RemoteRef
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_use_case import Harness, base_request
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.run_records import FakeRunRepositoryRecords, RecordsScope
from tests.unit.step_fixtures import a_context, a_row, a_worktree, an_environment, without

MODULES = (
    '[submodule "a"]\n\tpath = repos/a\n\turl = ../a.git\n'
    '[submodule "b"]\n\tpath = repos/b\n\turl = https://elsewhere/b.git\n'
)
BRANCH = "feat/hub"


def created_run(records: FakeRunRepositoryRecords, git: FakeGit | None = None) -> Run:
    harness = Harness(git=git or fixtures.repo_init_git())
    ports = replace(harness.ports, run_repositories=records)
    with harness.uow:
        return create_run(ports, base_request()).run


def member_context(
    run: Run, scope: RecordsScope, git: FakeGit, kind: str, **with_resolved: Any
) -> StepContext:
    row = a_row(kind=kind, with_resolved=with_resolved, path=f"{kind}-{len(with_resolved)}")
    row = row.model_copy(update={"run_id": run.id})
    environment = an_environment(run=run, worktrees=(a_worktree(branch=BRANCH),))
    ctx = a_context(row, git=git, env=environment)
    return without(ctx, record_writes=scope)


def test_create_run_writes_the_runs_own_row_from_the_plan_base_tip() -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)
    (own,) = records.rows
    assert (own.path, own.remote_url, own.base_branch) == (
        ".",
        fixtures.REPOSITORY.url,
        fixtures.BASE_BRANCH,
    )
    assert (own.run_id, own.branch) == (run.id, str(run.inputs.get("branch") or ""))
    assert own.base_tip == fixtures.BASE_SHA


def test_a_plan_that_did_not_read_the_base_has_its_tip_asked_once() -> None:
    run = created_run(FakeRunRepositoryRecords())
    unknown = FakeRunRepositoryRecords()
    record_own_repository(unknown, FakeGit(refs={}), run, "u", None)
    assert unknown.rows[0].base_tip == ""
    asked = FakeRunRepositoryRecords()
    git = FakeGit(refs={fixtures.BASE_BRANCH: "tip"})
    record_own_repository(asked, git, run, "u", None)
    assert asked.rows[0].base_tip == "tip" and len(git.called("ls_remote")) == 1
    record_own_repository(None, git, run, "u", None)
    assert len(git.called("ls_remote")) == 1


def test_three_rows_exist_once_the_first_rows_of_each_workdir_ran() -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)
    scope = RecordsScope(repositories=records)
    git = FakeGit(
        read_file=[MODULES],
        ls_remote=[RemoteRef(ref="main", sha="tipA"), RemoteRef(ref="main", sha="tipB")],
    )
    for path in ("repos/a", "repos/b"):
        ctx = member_context(run, scope, git, "git.submodule", workdir=path, branch=BRANCH)
        GitSubmoduleExecutor().execute(ctx)
    reads = (len(git.called("read_file")), len(git.called("ls_remote")))

    again = member_context(run, scope, git, "git.commit", workdir="repos/a", message="m")
    GitCommitExecutor().execute(again)

    by_path = {r.path: r for r in records.rows}
    assert sorted(by_path) == [".", "repos/a", "repos/b"]
    assert (by_path["repos/a"].remote_url, by_path["repos/a"].base_tip) == (
        "https://github.com/acme/a.git",
        "tipA",
    )
    assert (by_path["repos/b"].remote_url, by_path["repos/b"].base_tip) == (
        "https://elsewhere/b.git",
        "tipB",
    )
    assert by_path["repos/a"].base_branch == fixtures.BASE_BRANCH
    assert (len(git.called("read_file")), len(git.called("ls_remote"))) == reads


def test_each_push_sets_head_pushed_and_a_root_push_sets_the_root_row() -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)
    scope = RecordsScope(repositories=records)
    git = FakeGit(read_file=[MODULES], head_sha=["abc", "def", "root1"], push=["out"])
    push = member_context(run, scope, git, "git.push", workdir="repos/a", branch=BRANCH)
    GitPushExecutor().execute(push)
    assert next(r for r in records.rows if r.path == "repos/a").head_pushed == "abc"
    GitPushExecutor().execute(push)
    assert next(r for r in records.rows if r.path == "repos/a").head_pushed == "def"
    root = member_context(run, scope, git, "git.push", branch=BRANCH)
    GitPushExecutor().execute(root)
    assert next(r for r in records.rows if r.path == ".").head_pushed == "root1"


def test_a_push_that_parks_writes_nothing() -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)
    scope = RecordsScope(repositories=records)
    cases = (
        (FakeGit(push=[GitError(command="push", exit_code=1, output="no")]), {"branch": BRANCH}),
        (FakeGit(), {"branch": fixtures.BASE_BRANCH}),
        (FakeGit(push=[None]), {"branch": BRANCH, "workdir": "repos/a"}),
    )
    for git, with_resolved in cases:
        result = GitPushExecutor().execute(
            member_context(run, scope, git, "git.push", **with_resolved)
        )
        assert result.status == "error"
    assert scope.opens == 0
    assert all(r.head_pushed is None for r in records.rows)


@pytest.mark.parametrize("failing", ["open", "repository"])
def test_a_failing_record_scope_changes_no_result(failing: str) -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)

    def results(scope: RecordsScope | None) -> list[Any]:
        git = FakeGit(read_file=[MODULES], head_sha=["abc"], commit=["c1"], status=[" M f"])
        out = []
        for kind, with_resolved, executor in (
            ("git.submodule", {"workdir": "repos/a", "branch": BRANCH}, GitSubmoduleExecutor()),
            ("git.commit", {"workdir": "repos/a", "message": "m"}, GitCommitExecutor()),
            ("git.push", {"workdir": "repos/a", "branch": BRANCH}, GitPushExecutor()),
        ):
            ctx = member_context(run, scope or RecordsScope(), git, kind, **with_resolved)
            ctx = without(ctx, record_writes=scope)
            result = executor.execute(ctx)
            out.append(result.model_dump(exclude={"payload"}))
        return out

    broken = RecordsScope(fail_open=failing == "open")
    if failing == "repository":
        broken.repositories.fail = RuntimeError("down")
        broken.commits.fail = RuntimeError("down")
    assert results(broken) == results(None)


def test_without_a_scope_no_executor_makes_a_new_git_call() -> None:
    run = created_run(FakeRunRepositoryRecords())
    git = FakeGit(commit=["c1"], status=[" M f"], push=["out"], head_sha=["h"])
    for kind, with_resolved, executor in (
        ("git.commit", {"workdir": "repos/a", "message": "m"}, GitCommitExecutor()),
        ("git.push", {"workdir": "repos/a", "branch": BRANCH}, GitPushExecutor()),
    ):
        ctx = member_context(run, RecordsScope(), git, kind, **with_resolved)
        executor.execute(without(ctx, record_writes=None))
    assert git.called("read_file") == [] and git.called("ls_remote") == []
    assert git.called("head_sha") == []


def test_an_unreachable_remote_leaves_the_tip_empty_and_creation_unharmed() -> None:
    run = created_run(FakeRunRepositoryRecords())
    records = FakeRunRepositoryRecords()
    git = FakeGit(ls_remote=[GitError(command="ls-remote", exit_code=128, output="")])
    record_own_repository(records, git, run, "u", None)
    assert records.rows[0].base_tip == ""
