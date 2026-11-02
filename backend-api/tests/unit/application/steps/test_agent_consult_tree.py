"""`steps/agent_consult_tree.py` (story 1-4, spine AD-22, 2026-11-02): the clean snapshot an
offer takes of both trees, and the files a consult changed since, in AD-17's one spelling."""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps import agent_consult_tree
from orchestrator.domain.ports.git import Change
from tests.unit.application.steps.agent_fixtures import STORY_ID, WORKTREE, a_world, resolved
from tests.unit.fakes.git import FakeGit

MEMBER = f"{WORKTREE}/repos/member"


def test_a_root_row_snapshots_one_tree_after_sweeping_it() -> None:
    git = FakeGit(heads={WORKTREE: ["a" * 40]}, statuses={WORKTREE: ""}, status=[" M x.py", ""])
    world = a_world(git=git)

    snapshot = agent_consult_tree.sweep_and_snapshot(world.ctx, 4)

    assert snapshot == {"tree": {"head": "a" * 40, "status": ""}}
    assert world.git.called("commit") == []
    assert agent_consult_tree.WIP_MESSAGE.format(id=STORY_ID, n=4).endswith("(consult)")


def test_a_dirty_root_is_committed_under_the_consult_message() -> None:
    world = a_world(git=FakeGit(status=[" M x.py", ""], head_sha=["b" * 40]))

    agent_consult_tree.sweep_and_snapshot(world.ctx, 4)

    assert world.git.called("commit") == [
        (Path(WORKTREE), f"wip: story {STORY_ID} attempt 4 (consult)")
    ]


def test_an_unchanged_tree_names_nothing() -> None:
    world = a_world(git=FakeGit(heads={WORKTREE: ["a" * 40]}, statuses={WORKTREE: ""}))

    assert agent_consult_tree.changed(world.ctx, {"tree": {"head": "a" * 40, "status": ""}}) == ()


def test_a_workdir_change_is_named_run_root_relative_and_a_hub_change_as_is() -> None:
    git = FakeGit(
        heads={MEMBER: ["b" * 40], WORKTREE: ["c" * 40]},
        statuses={MEMBER: "", WORKTREE: "?? notes.md"},
        changes={MEMBER: (Change(path="src/a.py", kind="modified"),)},
    )
    world = a_world(git=git, with_resolved=resolved(workdir="repos/member"))
    snapshot = {
        "tree": {"head": "a" * 40, "status": ""},
        "root": {"head": "c" * 40, "status": ""},
    }

    assert agent_consult_tree.changed(world.ctx, snapshot) == ("notes.md", "repos/member/src/a.py")


def test_a_workdir_snapshot_missing_its_root_half_fails_closed() -> None:
    git = FakeGit(heads={MEMBER: ["a" * 40]}, statuses={MEMBER: ""})
    world = a_world(git=git, with_resolved=resolved(workdir="repos/member"))

    assert agent_consult_tree.changed(world.ctx, {"tree": {"head": "a" * 40, "status": ""}}) == (
        agent_consult_tree.NO_SNAPSHOT,
    )
