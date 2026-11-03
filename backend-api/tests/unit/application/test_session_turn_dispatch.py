"""`run_turn`, the `session_turn` step (story 2-5, AD-10, AD-14, AD-23).

A queued turn sweeps the trees on the session's first dispatch, writes the folder's
`.gitignore` and an empty reply file, records its start, then starts or resumes the senior
inside the attempt span, commits the group before waiting, and records the exit. `ended_at`
stays empty: the turn is busy until `session_commit` closes it. A recovered `running` turn is
killed and never dispatched again (hard rule 7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.rules.consult import IGNORE_ALL, IGNORE_FILE
from orchestrator.application.rules.session import REPLY_FILE, WIP_MESSAGE
from orchestrator.application.use_cases.session_dispatch import UNKNOWN_HARNESS
from orchestrator.application.use_cases.session_turn import INTERRUPTED, SESSION_CLOSED
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from tests.unit.application.session_fixtures import BUILD, MODEL, WORKTREE
from tests.unit.application.session_turn_fixtures import ROW, TurnWorld, a_result, a_turn_world
from tests.unit.fakes.git import FakeGit

TEXT = "Why is the route missing?"
OPENING = f"senior-session story specs/demo 1 stories[0] blocked intent gap\n{TEXT}"
START = "a" * 40


def posted(world: TurnWorld, text: str = TEXT):  # type: ignore[no-untyped-def]
    return world.attempt(world.post(text).attempt_id)


def test_the_first_turn_sweeps_writes_its_files_and_starts_a_new_session() -> None:
    git = FakeGit(status=[" M src/app.py", ""], head_sha=[START])
    world = a_turn_world(git=git, results=[a_result(session_id="s-new", exit_code=0)])
    turn = posted(world)
    commits_before = len(git.called("commit"))

    world.run(turn.id)

    assert git.called("commit")[commits_before:] == [(Path(WORKTREE), WIP_MESSAGE)]
    files = world.workspace(WORKTREE)
    assert files.read(IGNORE_FILE) == IGNORE_ALL
    assert files.read(REPLY_FILE) == ""
    (start,) = world.harness.called("start")
    assert start["prompt"] == OPENING
    assert start["cwd"] == Path(WORKTREE)
    assert start["model"] == MODEL
    assert (start["timeout_min"], start["stall_min"]) == (None, ROW["stall_min"])
    assert start["add_dirs"] == ()
    assert start["budget_usd_remaining"] == world.session.world.stored_run().budget_usd
    run_id = world.session.world.run.id
    assert start["log_path"] == Path(f"/work/logs/{run_id}/005-{turn.n}.log")
    assert start["env"]["ORCH_PROJECT"] == "demo"
    assert start["env"]["TRACEPARENT"] == world.harness_env.calls[-1]["traceparent"] != ""
    assert world.harness_env.calls[-1]["attempt"].id == turn.id
    assert world.harness.called("start_resume") == []
    stored = world.attempt(turn.id)
    assert (stored.status, stored.exit_code, stored.session_id) == ("done", 0, "s-new")
    assert stored.start_sha == START
    assert stored.log_path == "/work/x.log"
    assert stored.ended_at is None


def test_the_group_and_session_are_committed_before_the_wait() -> None:
    world = a_turn_world()
    turn = posted(world)
    seen: list[tuple[str | None, int | None, str]] = []

    def observe() -> None:
        stored = world.attempt(turn.id)
        seen.append((stored.session_id, stored.pgid, stored.status))

    world.harness.on_wait = observe

    world.run(turn.id)

    ((session_id, pgid, status),) = seen
    assert pgid == world.harness.pgid
    assert session_id == world.harness.called("start")[0]["session_id"]
    assert status == "running"
    run_id = world.session.world.run.id
    assert world.tracer.attempt_span_calls == [(run_id, BUILD, turn.id)]


def test_a_later_turn_resumes_the_earlier_session_with_the_text_alone() -> None:
    world = a_turn_world()
    world.session.turn(1, session_id="s-1", start_sha=START)
    turn = posted(world, "And the second route?")

    world.run(turn.id)

    assert world.harness.called("start") == []
    (resumed,) = world.harness.called("start_resume")
    assert (resumed["session_id"], resumed["message"]) == ("s-1", "And the second route?")
    assert resumed["model"] == MODEL
    assert world.git.called("commit") == []


def test_a_non_zero_exit_is_an_error_turn() -> None:
    world = a_turn_world(results=[a_result(exit_code=3)])
    turn = posted(world)

    world.run(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.exit_code, stored.ended_at) == ("error", 3, None)


def test_a_turn_with_no_tracer_still_dispatches() -> None:
    world = a_turn_world()
    world.traced = False
    turn = posted(world)

    world.run(turn.id)

    assert world.attempt(turn.id).status == "done"
    assert world.harness_env.calls[-1]["traceparent"] == ""


def test_a_git_failure_on_the_sweep_records_gits_words_and_dispatches_nothing() -> None:
    failure = GitError(command="git commit", exit_code=128, output="fatal: index.lock exists\n")
    world = a_turn_world(git=FakeGit(status=[" M a.py"], commit=[failure]))
    turn = posted(world)

    world.run(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", "fatal: index.lock exists")
    assert world.harness.calls == []


def test_an_unknown_harness_records_the_reason_and_dispatches_nothing() -> None:
    world = a_turn_world()
    turn = posted(world)
    world.writers.attempts.update(turn.model_copy(update={"harness": "gone"}))

    world.run(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", UNKNOWN_HARNESS.format(name="gone"))
    assert world.harness.calls == []


def test_a_turn_queued_on_a_session_that_closed_is_never_dispatched() -> None:
    world = a_turn_world()
    turn = posted(world)
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(
        run.model_copy(update={"status": "cancelled", "senior_session": False})
    )

    world.run(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", SESSION_CLOSED)
    assert world.harness.calls == []


def test_a_recovered_running_turn_is_killed_and_never_dispatched_again() -> None:
    world = a_turn_world()
    turn = world.session.turn(1, status="running", ended_at=None, pgid=917, session_id="s-1")
    lock = world.workspace(WORKTREE)
    lock.write(".git/index.lock", "")
    world.session.world.clock.on_sleep = lambda: lock.remove(".git/index.lock")

    world.run(turn.id)

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 917}]
    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", INTERRUPTED)
    run_id = world.session.world.run.id
    assert stored.log_path == f"/work/logs/{run_id}/005-1.log"
    assert stored.ended_at is None
    assert world.harness.calls == []


def test_a_recovered_turn_with_no_group_is_closed_without_a_kill() -> None:
    world = a_turn_world()
    turn = world.session.turn(1, status="running", ended_at=None)

    world.run(turn.id)

    assert world.process.called("kill_group") == []
    assert world.attempt(turn.id).output_ref == INTERRUPTED


@pytest.mark.parametrize("status", ["done", "error"])
def test_a_turn_that_already_ran_is_not_dispatched_again(status: str) -> None:
    world = a_turn_world()
    turn = world.session.turn(1, status=status, ended_at=None, exit_code=0)

    world.run(turn.id)

    assert world.attempt(turn.id) == turn
    assert world.harness.calls == []


def test_an_unknown_attempt_does_nothing() -> None:
    world = a_turn_world()

    world.run(new_id())

    assert world.harness.calls == []


def test_an_attempt_on_no_row_of_its_run_is_not_found() -> None:
    world = a_turn_world()
    stray = world.session.turn(1, step_run_id=new_id(), status="queued", ended_at=None)

    with pytest.raises(NotFound):
        world.run(stray.id)


def test_a_harness_that_raises_leaves_an_error_turn_naming_the_exception() -> None:
    world = a_turn_world()
    turn = posted(world)
    world.harness.on_wait = lambda: (_ for _ in ()).throw(OSError("no such file: claude"))

    world.run(turn.id)

    stored = world.attempt(turn.id)
    assert (stored.status, stored.output_ref) == ("error", "OSError: no such file: claude")
    assert stored.pgid == world.harness.pgid


def test_a_lost_group_write_kills_the_group_and_records_the_failure() -> None:
    world = a_turn_world()
    turn = posted(world)
    world.failing_write = world.writes + 2

    world.run(turn.id)

    assert world.process.called("kill_group") == [
        {"method": "kill_group", "pgid": world.harness.pgid}
    ]
    stored = world.attempt(turn.id)
    assert stored.status == "error"
    assert stored.output_ref == f"RuntimeError: attempt write {world.failing_write} failed"
    assert world.harness.called("wait") == []


def test_a_workdir_turn_runs_in_the_member_and_reaches_the_hub() -> None:
    member = f"{WORKTREE}/repos/m"
    git = FakeGit(
        statuses={member: " M src/x.py", WORKTREE: ""},
        heads={member: ["m" * 40], WORKTREE: ["h" * 40]},
    )
    world = a_turn_world(git=git, with_resolved={**ROW, "workdir": "repos/m"})
    turn = posted(world)

    world.run(turn.id)

    assert git.called("commit") == [(Path(WORKTREE), WIP_MESSAGE, "repos/m")]
    assert world.workspace(member).read(REPLY_FILE) == ""
    (start,) = world.harness.called("start")
    assert (start["cwd"], start["add_dirs"]) == (Path(member), (Path(WORKTREE),))
    assert "specs/demo" in start["prompt"].splitlines()[0]
    stored = world.attempt(turn.id)
    assert (stored.start_sha, stored.root_start_sha) == ("m" * 40, "h" * 40)
