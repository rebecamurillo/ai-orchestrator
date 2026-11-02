"""Story 2-5 review, 2026-11-02: the turn's file writes refuse links on a real tree, a
cancel racing the group's commit still kills the group, only a dispatched turn is committed,
and a failure late in the commit keeps what the turn already reached (AD-14, AD-22, AD-23)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.application.rules.consult import IGNORE_FILE
from orchestrator.application.rules.session import REPLY_FILE, WIP_MESSAGE
from orchestrator.application.use_cases.session_dispatch import UNDER_LINK
from orchestrator.application.use_cases.session_turn import SESSION_CLOSED
from orchestrator.domain.ports.git import GitError
from orchestrator.infrastructure.workspace import FsWorkspace
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world
from tests.unit.fakes.git import FakeGit

END = "e" * 40


def on_disk(tmp_path: Path, git: FakeGit | None = None) -> tuple[TurnWorld, Path]:
    tree = tmp_path / "wt"
    tree.mkdir()
    world = a_turn_world(git=git, worktree_path=str(tree))
    world.workspace_factory = FsWorkspace
    return world, tree


# ── links ────────────────────────────────────────────────────────────────────


def test_a_reply_file_that_is_a_link_is_replaced_and_its_target_left_alone(
    tmp_path: Path,
) -> None:
    world, tree = on_disk(tmp_path)
    secret = tmp_path / "agent" / "credentials.json"
    secret.parent.mkdir()
    secret.write_text('{"token": "keep"}')
    reply = tree / REPLY_FILE
    reply.parent.mkdir(parents=True)
    reply.symlink_to(secret)
    ignore = tree / IGNORE_FILE
    ignore.unlink(missing_ok=True)
    ignore.symlink_to(secret)
    turn = world.post()

    world.run(turn.attempt_id)

    assert secret.read_text() == '{"token": "keep"}'
    assert not reply.is_symlink()
    assert reply.read_text() == ""
    assert not ignore.is_symlink()
    assert world.attempt(turn.attempt_id).status == "done"


def test_a_reply_folder_that_is_a_link_refuses_the_turn(tmp_path: Path) -> None:
    world, tree = on_disk(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "reply.md").write_text("theirs")
    (tree / ".orchestrator").mkdir()
    (tree / ".orchestrator" / "session").symlink_to(outside, target_is_directory=True)
    turn = world.post()

    world.run(turn.attempt_id)

    stored = world.attempt(turn.attempt_id)
    assert (stored.status, stored.output_ref) == ("error", UNDER_LINK)
    assert (outside / "reply.md").read_text() == "theirs"
    assert world.harness.calls == []


def test_an_undecodable_reply_is_read_with_replacements_and_keeps_the_turn_done(
    tmp_path: Path,
) -> None:
    world, tree = on_disk(tmp_path, git=FakeGit(head_sha=["a" * 40, END]))
    turn = world.post()
    world.harness.on_wait = lambda: (tree / REPLY_FILE).write_bytes(b"ok \xff\xfe done")
    world.run(turn.attempt_id)

    world.commit(turn.attempt_id)

    stored = world.attempt(turn.attempt_id)
    assert stored.reply == "ok �� done"
    assert (stored.status, stored.end_sha) == ("done", END)
    assert stored.ended_at is not None


# ── the cancel race ──────────────────────────────────────────────────────────


def test_a_cancel_landing_before_the_group_is_committed_kills_the_group() -> None:
    world = a_turn_world()
    turn = world.post()
    start = world.harness.start
    plans: list[Any] = []

    def cancelled_first(**kwargs: Any) -> Any:
        plans.append(world.session.send("cancel").cancel_plan)
        return start(**kwargs)

    world.harness.start = cancelled_first  # type: ignore[method-assign]

    world.run(turn.attempt_id)

    (plan,) = plans
    assert world.harness.pgid not in plan.pgids
    assert world.process.called("kill_group") == [
        {"method": "kill_group", "pgid": world.harness.pgid}
    ]
    stored = world.attempt(turn.attempt_id)
    assert (stored.status, stored.output_ref) == ("error", SESSION_CLOSED)
    assert stored.pgid == world.harness.pgid
    assert world.session.world.stored_run().status == "cancelled"


# ── only a dispatched turn is committed ─────────────────────────────────────


def test_a_turn_that_never_dispatched_commits_nothing() -> None:
    git = FakeGit(status=[" M left/over.py"])
    world = a_turn_world(git=git)
    turn = world.post()
    stored = world.attempt(turn.attempt_id)
    world.writers.attempts.update(stored.model_copy(update={"harness": "gone"}))
    world.run(turn.attempt_id)

    world.commit(turn.attempt_id)

    assert git.called("commit") == []
    closed = world.attempt(turn.attempt_id)
    assert closed.status == "error"
    assert closed.ended_at is not None


def test_a_turn_whose_wip_sweep_failed_is_not_committed_as_a_turn() -> None:
    failure = GitError(command="git commit", exit_code=1, output="error: cannot lock ref\n")
    git = FakeGit(status=[" M left/over.py"], commit=[failure, "c" * 40])
    world = a_turn_world(git=git)
    turn = world.post()
    world.run(turn.attempt_id)

    world.commit(turn.attempt_id)

    assert [message for _tree, message in git.called("commit")] == [WIP_MESSAGE]
    assert world.attempt(turn.attempt_id).output_ref == "error: cannot lock ref"


# ── a late failure keeps what the turn reached ───────────────────────────────


def test_a_failing_reply_read_keeps_the_end_shas_and_the_done_status() -> None:
    world = a_turn_world(git=FakeGit(head_sha=["a" * 40, END]))
    turn = world.post()
    world.run(turn.attempt_id)
    workspace = world.workspace()

    def broken(path: str, **_kwargs: Any) -> str | None:
        raise OSError("disk gone")

    workspace.read = broken  # type: ignore[method-assign]

    world.commit(turn.attempt_id)

    stored = world.attempt(turn.attempt_id)
    assert (stored.status, stored.end_sha, stored.reply) == ("done", END, "")
    assert stored.output_ref == "OSError: disk gone"
    assert stored.ended_at is not None
