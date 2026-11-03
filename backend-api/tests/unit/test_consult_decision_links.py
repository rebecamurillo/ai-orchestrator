"""Links at a consult's own paths, on the real filesystem (story 1-5 review, 2026-11-02, spine
AD-14/AD-22).

`FsWorkspace.remove` deletes a link itself, never what it points to, and a dangling one too:
`exists()` follows links, so a planted dangling link used to survive the clean-up and be read
once something wrote its target. `is_link` names a path that is a link or lies under one, and
the consult never reads such a decision file."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.workspace import WorkspaceError
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.workspace.fs import FsWorkspace
from tests.unit.application.consult_fixtures import DECISION, QUESTION, World, a_consult_world
from tests.unit.application.test_consult_approval_run import approving, with_anchors

APPROVAL = approving("[tests/a.py]", reason="AC 2 changes it")
STORY_COPY = ".orchestrator/consult/003-2.story.md"


# ── FsWorkspace ──────────────────────────────────────────────────────────────


def test_remove_deletes_a_dangling_link(tmp_path: Path) -> None:
    link = tmp_path / "planted.md"
    link.symlink_to(tmp_path / "not-yet.md")

    FsWorkspace(str(tmp_path)).remove("planted.md")

    assert not link.is_symlink()


def test_remove_deletes_a_link_and_leaves_its_target(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("kept")
    (tmp_path / "link.md").symlink_to(tmp_path / "target.md")

    FsWorkspace(str(tmp_path)).remove("link.md")

    assert not (tmp_path / "link.md").is_symlink()
    assert (tmp_path / "target.md").read_text() == "kept"


def test_remove_deletes_a_folder_link_and_leaves_the_folder(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.md").write_text("kept")
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)

    FsWorkspace(str(tmp_path)).remove("linked")

    assert not (tmp_path / "linked").is_symlink()
    assert (tmp_path / "real" / "a.md").read_text() == "kept"


def test_is_link_names_a_link_and_a_path_under_a_linked_folder(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.md").write_text("x")
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
    (tmp_path / "file.md").symlink_to(tmp_path / "gone.md")
    (tmp_path / "plain.md").write_text("x")
    workspace = FsWorkspace(str(tmp_path))

    assert workspace.is_link("file.md")
    assert workspace.is_link("linked")
    assert workspace.is_link("linked/a.md")
    assert not workspace.is_link("plain.md")
    assert not workspace.is_link("real/a.md")
    assert not workspace.is_link("never/was.md")


def test_is_link_refuses_outside_the_root(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        FsWorkspace(str(tmp_path)).is_link("../secret")


# ── the consult, on a real tree ──────────────────────────────────────────────


def on_disk(world: World, root: Path) -> World:
    workspace = FsWorkspace(str(root))
    ports = replace(world.ctx.ports, workspace=lambda _tree: workspace)
    return replace(world, ctx=replace(world.ctx, ports=ports))


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def test_a_planted_dangling_link_is_removed_before_its_target_is_written(tmp_path: Path) -> None:
    """The reviewer's case: the agent links the decision path to a file that does not exist
    yet, and something it left behind writes that file while the senior runs."""
    world = on_disk(with_anchors(a_consult_world()), tmp_path)
    decision = tmp_path / DECISION
    decision.parent.mkdir(parents=True)
    decision.symlink_to(tmp_path / "elsewhere.md")
    world.harness.on_wait = lambda: (tmp_path / "elsewhere.md").write_text(APPROVAL)

    result = run(world)

    assert result.reason == f"{QUESTION} · consult failed: no readable decision"
    assert result.consult is not None
    assert result.consult.approved_files == ()
    assert not decision.is_symlink()


def test_a_link_made_while_the_senior_runs_is_never_read(tmp_path: Path) -> None:
    world = on_disk(with_anchors(a_consult_world()), tmp_path)
    (tmp_path / "elsewhere.md").write_text(APPROVAL)
    decision = tmp_path / DECISION

    def the_link_appears() -> None:
        decision.parent.mkdir(parents=True, exist_ok=True)
        decision.symlink_to(tmp_path / "elsewhere.md")

    world.harness.on_wait = the_link_appears

    result = run(world)

    assert result.reason == f"{QUESTION} · consult failed: no readable decision"


def test_a_planted_baseline_link_is_removed_and_its_target_left_alone(tmp_path: Path) -> None:
    world = on_disk(with_anchors(a_consult_world()), tmp_path)
    copy = tmp_path / STORY_COPY
    copy.parent.mkdir(parents=True)
    (tmp_path / "target.md").write_text("kept")
    copy.symlink_to(tmp_path / "target.md")

    run(world)

    assert not copy.is_symlink()
    assert (tmp_path / "target.md").read_text() == "kept"


def test_the_seniors_own_file_is_read(tmp_path: Path) -> None:
    world = on_disk(with_anchors(a_consult_world()), tmp_path)
    world.harness.on_wait = lambda: FsWorkspace(str(tmp_path)).write(DECISION, APPROVAL)

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert result.consult.approved_files == ("tests/a.py",)
