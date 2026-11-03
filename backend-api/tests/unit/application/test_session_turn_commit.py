"""`commit_turn`, the `session_commit` step (story 2-5, AD-8, AD-11, AD-23).

It runs on every path. Unless the Run is terminal, each tree the turn spans is committed as
`session: turn {k} (orchestrator)`; the reply file is stored, capped at 64 KiB; the end SHAs
and `ended_at` close the turn; and the spend is written over the Run read under the row
lock, so a concurrent `cancel` is never overwritten. A re-run after a crash commits nothing.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from orchestrator.application.rules.session import REPLY_FILE, REPLY_LIMIT, TURN_MESSAGE
from orchestrator.application.use_cases.session_turn import INTERRUPTED, commit_turn
from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.domain.ports.git import GitError
from tests.unit.application.session_fixtures import WORKTREE
from tests.unit.application.session_turn_fixtures import ROW, TurnWorld, a_turn_world
from tests.unit.fakes.git import FakeGit

END = "e" * 40
COST = Decimal("0.420000")


def ran(world: TurnWorld, reply: str | None = "The route is in `api/v2`.") -> object:
    turn = world.attempt(world.post().attempt_id)
    if reply is not None:
        world.harness.on_wait = lambda: world.workspace(WORKTREE).write(REPLY_FILE, reply)
    world.run(turn.id)
    return turn.id


def priced(world: TurnWorld, attempt_id: object) -> None:
    world.gateway.script(
        world.session.world.run.id,
        attempt_id,  # type: ignore[arg-type]
        AttemptSpend(
            usd=COST, tokens_in=100, tokens_out=50, by_model=(), calls=1, provisional=False
        ),
    )


def test_a_turn_is_committed_stored_closed_and_billed() -> None:
    git = FakeGit(status=["", " M src/app.py"], heads={WORKTREE: ["a" * 40, END]})
    world = a_turn_world(git=git)
    attempt_id = ran(world)
    priced(world, attempt_id)

    world.commit(attempt_id)  # type: ignore[arg-type]

    run_id = world.session.world.run.id
    spent = world.session.world.ports.runs.calls[-2:]  # type: ignore[attr-defined]
    assert spent == [("get_for_update", run_id), ("update", run_id)]
    assert git.called("commit") == [(Path(WORKTREE), TURN_MESSAGE.format(k=1))]
    stored = world.attempt(attempt_id)  # type: ignore[arg-type]
    assert stored.reply == "The route is in `api/v2`."
    assert (stored.end_sha, stored.ended_at) == (END, world.session.world.clock.now())
    assert (stored.status, stored.cost_usd) == ("done", COST)
    run = world.session.world.stored_run()
    assert run.spend_usd == COST
    assert run.status == "needs_you"
    assert world.spend_uows[-1].committed


def test_the_turn_number_counts_the_sessions_attempts() -> None:
    git = FakeGit(status=[" M a.py"])
    world = a_turn_world(git=git)
    world.session.turn(1, session_id="s-1", start_sha="a" * 40)
    attempt_id = ran(world)

    world.commit(attempt_id)  # type: ignore[arg-type]

    assert git.called("commit") == [(Path(WORKTREE), TURN_MESSAGE.format(k=2))]


def test_a_hub_turn_commits_each_tree_it_edited_on_its_own() -> None:
    member = f"{WORKTREE}/repos/m"
    git = FakeGit(statuses={member: " M src/x.py", WORKTREE: " M specs/demo/notes.md"})
    world = a_turn_world(git=git, with_resolved={**ROW, "workdir": "repos/m"})
    attempt_id = ran(world, reply=None)
    commits_before = len(git.called("commit"))

    world.commit(attempt_id)  # type: ignore[arg-type]

    message = TURN_MESSAGE.format(k=1)
    assert git.called("commit")[commits_before:] == [
        (Path(WORKTREE), message, "repos/m"),
        (Path(WORKTREE), message),
    ]


def test_a_git_failure_is_recorded_and_the_turn_still_closes() -> None:
    failure = GitError(command="git commit", exit_code=1, output="error: cannot lock ref\n")
    git = FakeGit(status=["", " M a.py"], commit=[failure])
    world = a_turn_world(git=git)
    attempt_id = ran(world)

    world.commit(attempt_id)  # type: ignore[arg-type]

    stored = world.attempt(attempt_id)  # type: ignore[arg-type]
    assert (stored.status, stored.output_ref) == ("error", "error: cannot lock ref")
    assert stored.ended_at is not None
    assert stored.reply == "The route is in `api/v2`."


def test_a_missing_reply_file_stores_an_empty_reply() -> None:
    world = a_turn_world()
    attempt_id = ran(world, reply=None)
    world.workspace(WORKTREE).remove(REPLY_FILE)

    world.commit(attempt_id)  # type: ignore[arg-type]

    assert world.attempt(attempt_id).reply == ""  # type: ignore[arg-type]


def test_a_reply_that_is_a_link_is_not_read() -> None:
    world = a_turn_world()
    attempt_id = ran(world)
    world.workspace(WORKTREE).links.add(REPLY_FILE)

    world.commit(attempt_id)  # type: ignore[arg-type]

    assert world.attempt(attempt_id).reply == ""  # type: ignore[arg-type]


def test_a_long_reply_is_capped() -> None:
    world = a_turn_world()
    attempt_id = ran(world, reply="x" * (REPLY_LIMIT + 10))

    world.commit(attempt_id)  # type: ignore[arg-type]

    assert world.attempt(attempt_id).reply == "x" * REPLY_LIMIT  # type: ignore[arg-type]


def test_a_cancelled_run_is_not_committed_but_the_turn_is_closed_and_billed() -> None:
    git = FakeGit(status=["", " M a.py"])
    world = a_turn_world(git=git)
    attempt_id = ran(world)
    priced(world, attempt_id)
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(
        run.model_copy(update={"status": "cancelled", "senior_session": False})
    )

    world.commit(attempt_id)  # type: ignore[arg-type]

    assert git.called("commit") == []
    stored = world.attempt(attempt_id)  # type: ignore[arg-type]
    assert stored.ended_at is not None
    after = world.session.world.stored_run()
    assert (after.status, after.spend_usd) == ("cancelled", COST)


def test_a_turn_left_open_by_a_crash_closes_as_an_interrupted_error() -> None:
    world = a_turn_world()
    turn = world.session.turn(1, status="running", ended_at=None)

    world.commit(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", INTERRUPTED)
    assert stored.ended_at is not None


def test_an_open_turn_keeps_a_reason_it_already_recorded() -> None:
    world = a_turn_world()
    turn = world.session.turn(1, status="queued", ended_at=None, output_ref="queue unavailable")

    world.commit(turn.id)

    assert world.attempt(turn.id).output_ref == "queue unavailable"


def test_an_unexpected_failure_still_closes_the_turn_naming_it() -> None:
    # Story 2-5 review, 2026-11-02: a finished turn is never downgraded by a late failure,
    # and the parts of the close after it still run.
    world = a_turn_world(git=FakeGit(head_sha=["a" * 40, END]))
    attempt_id = ran(world)
    world.git._scripts["status"] = [ValueError("porcelain unreadable")]

    world.commit(attempt_id)  # type: ignore[arg-type]

    stored = world.attempt(attempt_id)  # type: ignore[arg-type]
    assert (stored.status, stored.output_ref) == ("done", "ValueError: porcelain unreadable")
    assert (stored.end_sha, stored.reply) == (END, "The route is in `api/v2`.")
    assert stored.ended_at is not None


def test_a_rerun_after_a_crash_commits_nothing_and_bills_once() -> None:
    git = FakeGit(status=["", " M a.py", ""])
    world = a_turn_world(git=git)
    attempt_id = ran(world)
    priced(world, attempt_id)

    world.commit(attempt_id)  # type: ignore[arg-type]
    world.commit(attempt_id)  # type: ignore[arg-type]

    assert len(git.called("commit")) == 1
    assert world.session.world.stored_run().spend_usd == COST


def test_an_unknown_attempt_does_nothing() -> None:
    world = a_turn_world()

    world.commit(new_id())

    assert world.spend_uows == []


def test_a_process_wired_without_spend_writes_still_closes_the_turn() -> None:
    world = a_turn_world()
    attempt_id = ran(world)
    ports = world.ports

    commit_turn(replace(ports, step=replace(ports.step, spend_writes=None)), attempt_id)  # type: ignore[arg-type]

    assert world.attempt(attempt_id).ended_at is not None  # type: ignore[arg-type]
    assert world.spend_uows == []


def test_a_locked_spend_write_keeps_a_cancel_that_committed_first() -> None:
    world = a_turn_world()
    attempt_id = ran(world)
    priced(world, attempt_id)
    stale = world.session.world.stored_run()
    world.session.world.ports.runs.update(stale.model_copy(update={"status": "cancelled"}))
    finished = world.attempt(attempt_id)  # type: ignore[arg-type]

    with world._spend_writes() as ports:
        updated = record_attempt_spend(ports, stale, finished, None, locked=True)

    stored = world.session.world.stored_run()
    assert (stored.status, stored.spend_usd) == ("cancelled", COST)
    assert updated == stored
