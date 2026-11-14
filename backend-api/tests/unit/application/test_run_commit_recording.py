"""Every commit the orchestrator makes is a `run_commit` row (story 2, AC3, AC4)."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from orchestrator.application.steps import agent_consult_tree, agent_prepare, agent_workdir
from orchestrator.application.steps.context import ProjectContext, StepContext
from orchestrator.application.steps.git_commit import GitCommitExecutor
from orchestrator.application.steps.git_merge import GitMergeExecutor
from orchestrator.application.use_cases.run_files import write_run_file
from orchestrator.domain.ports.git import NO_UPSTREAM
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    World,
    a_world,
    an_attempt,
)
from tests.unit.application.steps.test_agent_workdir import (
    MEMBER,
    WORKDIR,
    a_workdir_git,
    a_workdir_world,
)
from tests.unit.application.test_run_files_write import (
    NEW_CONTENT,
    SPEC_FILE,
    a_run,
    ports_for,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.run_records import FakeRunCommitRepository, RecordsScope
from tests.unit.step_fixtures import a_context, a_row, a_worktree, an_environment


def recorded(ctx: StepContext, scope: RecordsScope) -> StepContext:
    return replace(ctx, ports=replace(ctx.ports, record_writes=scope))


def rows(scope: RecordsScope) -> list[tuple[str, str, str]]:
    return [(c.path, c.sha, c.made_by) for c in scope.commits.commits]


def an_agent(world: World, scope: RecordsScope) -> StepContext:
    previous = an_attempt(world.row, 1, status="error")
    return replace(recorded(world.ctx, scope), previous_attempt=previous)


def test_a_wip_commit_in_both_trees_is_recorded_wip_at_each_path() -> None:
    scope = RecordsScope()
    git = a_workdir_git(
        statuses={MEMBER: " M a"}, status_ignoring_submodules=[" M b"], commit=["m1", "r1"]
    )
    world = a_workdir_world(git=git)

    assert agent_workdir.wip_commit(an_agent(world, scope)) is None

    assert rows(scope) == [(WORKDIR, "m1", "wip"), (".", "r1", "wip")]


def test_a_root_wip_commit_and_a_none_commit() -> None:
    scope = RecordsScope()
    world = a_world(git=FakeGit(status=[" M a"], commit=[None]))
    assert agent_workdir.wip_commit(an_agent(world, scope)) is None
    assert rows(scope) == []
    world = a_world(git=FakeGit(status=[" M a"], commit=["w1"]))
    agent_workdir.wip_commit(an_agent(world, scope))
    assert rows(scope) == [(".", "w1", "wip")]


def test_the_prepare_commit_is_recorded_prepare() -> None:
    scope = RecordsScope()
    project = ProjectContext(context_text="ctx", context_paths=())
    git = FakeGit(status=["A  specs/notifications/project-context.md", ""], commit=["p1"])
    world = a_world(project=project, git=git)

    assert agent_prepare.writes(recorded(world.ctx, scope)) is None

    assert rows(scope) == [(".", "p1", "prepare")]


def test_a_consult_sweep_is_recorded_wip() -> None:
    scope = RecordsScope()
    world = a_world(git=FakeGit(status=[" M a"], commit=["c1"], head_sha=[HEAD_SHA]))
    agent_consult_tree.sweep_and_snapshot(recorded(world.ctx, scope), 1)
    assert rows(scope) == [(".", "c1", "wip")]


def a_git_context(git: FakeGit, scope: RecordsScope, **with_resolved: Any) -> StepContext:
    row = a_row(kind="git.commit", with_resolved={"message": "m", **with_resolved})
    environment = an_environment(worktrees=(a_worktree(),))
    return recorded(a_context(row, git=git, env=environment), scope)


def test_git_commit_root_and_workdir_forms_are_recorded() -> None:
    scope = RecordsScope()
    root = a_git_context(FakeGit(status=[" M f"], commit=["g1"]), scope)
    GitCommitExecutor().execute(root)
    member = a_git_context(FakeGit(status=[" M f"], commit=["g2"]), scope, workdir="./repos/m/")
    GitCommitExecutor().execute(member)
    assert rows(scope) == [(".", "g1", "git.commit"), ("repos/m", "g2", "git.commit")]
    assert [r.path for r in scope.repositories.rows] == ["repos/m"]


def test_a_commit_that_answers_none_adds_nothing() -> None:
    scope = RecordsScope()
    GitCommitExecutor().execute(a_git_context(FakeGit(status=[" M f"], commit=[None]), scope))
    assert rows(scope) == []


def test_git_merge_records_a_real_merge_and_nothing_else() -> None:
    for answer, expected in (("merged", [(".", "m1", "git.merge")]), (NO_UPSTREAM, []), (None, [])):
        scope = RecordsScope()
        row = a_row(kind="git.merge", with_resolved={"from": "main"})
        environment = an_environment(worktrees=(a_worktree(),))
        ctx = recorded(
            a_context(row, git=FakeGit(merge=[answer], head_sha=["m1"]), env=environment), scope
        )
        GitMergeExecutor().execute(ctx)
        assert rows(scope) == expected


class Recording(TurnWorld):
    """A turn world whose step ports carry a record scope."""

    scope: RecordsScope = RecordsScope()

    @property
    def step(self):  # type: ignore[no-untyped-def]
        return replace(TurnWorld.step.fget(self), record_writes=self.scope)  # type: ignore[attr-defined]


def test_a_session_turn_records_its_dispatch_sweep_and_its_turn_commit_as_session() -> None:
    plain = a_turn_world(git=FakeGit(status=[" M a"], commit=["s1", "s2"]))
    world = Recording(**{f.name: getattr(plain, f.name) for f in fields(plain)})
    world.scope = RecordsScope()
    world.turn()
    assert [(made_by, sha) for _, sha, made_by in rows(world.scope)] == [
        ("session", "s1"),
        ("session", "s2"),
    ]


def test_an_operator_edit_is_recorded_in_the_same_unit_of_work() -> None:
    run = a_run()
    ports, _runs, records, uow = ports_for(run, {SPEC_FILE: "old"}, git=FakeGit(commit=["e1"]))
    commits = FakeRunCommitRepository()
    write_run_file(replace(ports, run_commits=commits), run.id, SPEC_FILE, NEW_CONTENT)
    assert [(c.path, c.sha, c.made_by) for c in commits.commits] == [(".", "e1", "operator_edit")]
    assert uow.committed and len(records.list_for_run(run.id)) == 1


def test_an_operator_edit_without_a_repository_or_a_sha_records_nothing() -> None:
    run = a_run()
    ports, *_ = ports_for(run, {SPEC_FILE: "old"}, git=FakeGit(commit=[None]))
    commits = FakeRunCommitRepository()
    write_run_file(replace(ports, run_commits=commits), run.id, SPEC_FILE, NEW_CONTENT)
    assert commits.commits == []
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})
    write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)


def test_the_same_sha_twice_stays_one_row() -> None:
    scope = RecordsScope()
    git = FakeGit(status=[" M a"], commit=["same"])
    world = a_world(git=git)
    agent_consult_tree.sweep_and_snapshot(recorded(world.ctx, scope), 1)
    agent_consult_tree.sweep_and_snapshot(recorded(world.ctx, scope), 2)
    assert len(rows(scope)) == 1
