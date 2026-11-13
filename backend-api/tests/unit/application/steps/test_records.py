"""`note_member`, `note_commits`, `note_head_commit`, `note_pushed` (story 2, AC1-AC3, AC7)."""

from __future__ import annotations

from pathlib import Path

from structlog.testing import capture_logs

from orchestrator.application.steps import records
from orchestrator.application.steps.context import StepContext
from orchestrator.domain.ports.git import GitError, RemoteRef
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.run_records import RecordsScope
from tests.unit.step_fixtures import a_context, a_row, a_worktree, an_environment, without

TWO_SCOPES = 2
FOUR_NOTES = 4
GITMODULES = '[submodule "a"]\n\tpath = repos/a\n\turl = ../a.git\n'


def context(scope: RecordsScope | None, git: FakeGit, **env: object) -> StepContext:
    row = a_row(kind="git.push", with_resolved={"branch": "feat/x"})
    base = an_context(row, git, **env)
    return without(base, record_writes=scope)


def an_context(row, git: FakeGit, **env: object) -> StepContext:  # type: ignore[no-untyped-def]
    environment = an_environment(worktrees=(a_worktree(),), **env)
    return a_context(row, git=git, env=environment)


def test_without_a_scope_nothing_calls_git() -> None:
    git = FakeGit()
    ctx = context(None, git)
    records.note_member(ctx, "repos/a")
    records.note_commits(ctx, ((".", "s"),), "wip")
    records.note_head_commit(ctx, ".", Path("/x"), "git.merge")
    records.note_pushed(ctx, ".", Path("/x"))
    assert git.calls == []


def test_a_member_is_written_once_from_gitmodules_and_the_remote_tip() -> None:
    scope = RecordsScope()
    git = FakeGit(read_file=[GITMODULES], ls_remote=[RemoteRef(ref="main", sha="tip")])
    ctx = context(scope, git)
    records.note_member(ctx, "./repos/a/")
    records.note_member(ctx, "repos/a")
    (row,) = scope.repositories.rows
    assert (row.path, row.remote_url, row.base_branch, row.base_tip) == (
        "repos/a",
        "https://github.com/acme/a.git",
        "main",
        "tip",
    )
    assert len(git.called("read_file")) == 1 and len(git.called("ls_remote")) == 1
    assert scope.units[0].committed


def test_a_member_without_a_url_or_a_tip_is_recorded_with_empty_strings() -> None:
    scope = RecordsScope()
    git = FakeGit(read_file=[None])
    records.note_member(context(scope, git), "repos/a")
    assert scope.repositories.rows[0].remote_url == ""
    assert scope.repositories.rows[0].base_tip == ""
    assert git.called("ls_remote") == []
    scope2 = RecordsScope()
    records.note_member(
        context(scope2, FakeGit(read_file=[GITMODULES], ls_remote=[None])), "repos/a"
    )
    assert scope2.repositories.rows[0].base_tip == ""


def test_the_member_takes_the_run_branch_from_the_row_when_the_run_has_none() -> None:
    scope = RecordsScope()
    row = a_row(kind="agent", with_resolved={"branch": "feat/x"})
    ctx = without(an_context(row, FakeGit(read_file=[None])), record_writes=scope)
    records.note_member(ctx, "repos/a")
    assert scope.repositories.rows[0].branch == "feat/x"


def test_commits_record_the_non_none_shas_once() -> None:
    scope = RecordsScope()
    ctx = context(scope, FakeGit())
    records.note_commits(ctx, ((".", "s1"), ("./repos/a/", "s2"), (".", None)), "wip")
    records.note_commits(ctx, ((".", "s1"),), "wip")
    records.note_commits(ctx, ((".", None),), "wip")
    assert [(c.path, c.sha, c.made_by) for c in scope.commits.commits] == [
        (".", "s1", "wip"),
        ("repos/a", "s2", "wip"),
    ]
    assert scope.opens == TWO_SCOPES


def test_head_commit_records_the_trees_head() -> None:
    scope = RecordsScope()
    git = FakeGit(head_sha=["h"])
    records.note_head_commit(context(scope, git), ".", Path("/wt"), "git.merge")
    assert scope.commits.commits[0].sha == "h"


def test_pushed_sets_head_pushed_and_skips_an_unknown_head() -> None:
    scope = RecordsScope()
    ctx = context(scope, FakeGit(head_sha=["abc"]))
    records.note_member(ctx, "repos/a")
    records.note_pushed(ctx, "repos/a", Path("/wt/repos/a"))
    assert scope.repositories.rows[0].head_pushed == "abc"
    none = RecordsScope()
    records.note_pushed(context(none, FakeGit(head_sha=[None])), ".", Path("/wt"))
    assert none.opens == 0


def test_a_failing_scope_or_repository_is_logged_and_swallowed() -> None:
    for scope in (RecordsScope(fail_open=True), _failing()):
        ctx = context(scope, FakeGit(head_sha=["h"], read_file=[GITMODULES]))
        with capture_logs() as logs:
            records.note_member(ctx, "repos/a")
            records.note_commits(ctx, ((".", "s"),), "wip")
            records.note_head_commit(ctx, ".", Path("/wt"), "wip")
            records.note_pushed(ctx, ".", Path("/wt"))
        assert len([e for e in logs if e["event"] == records.RECORD_FAILED]) == FOUR_NOTES


def test_a_raising_head_read_is_logged_by_note_head_commit() -> None:
    ctx = context(RecordsScope(), FakeGit(head_sha=[GitError(command="x", exit_code=1, output="")]))
    with capture_logs() as logs:
        records.note_head_commit(ctx, ".", Path("/wt"), "wip")
    assert [e["what"] for e in logs] == ["head"]


def _failing() -> RecordsScope:
    scope = RecordsScope()
    scope.repositories.fail = RuntimeError("down")
    scope.commits.fail = RuntimeError("down")
    return scope
