"""`cancel_initiative` (epic 7 story 3, AC9-AC12), on the shared fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.use_cases import initiatives as use_cases
from orchestrator.application.use_cases.initiatives import cancel_initiative
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Worktree
from tests.unit.application.initiative_world import HUB_SHA, InitiativeWorld
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.initiative_fixtures import AT, a_run

BRANCH = "spec/snake-v3"
TWO_COMMITS = 2


def a_live_run(world: InitiativeWorld, initiative: Initiative, **overrides: Any) -> Run:
    values: dict[str, Any] = {
        "project_id": world.project.id,
        "repository_id": world.hub.id,
        "initiative_id": initiative.id,
        "initiative_round": 1,
        "initiative_position": 0,
        "status": "needs_you",
        "park_kind": "conversation",
        "budget_usd": None,
    }
    values.update(overrides)
    return a_run(**values)


def cancel(world: InitiativeWorld, initiative: Initiative) -> Initiative:
    with world.uow:
        return cancel_initiative(world.ports, initiative.id)


def deletes(world: InitiativeWorld) -> list[Any]:
    return [args for call, args in world.git.calls if call == "delete_remote_branch"]


def world_with(
    initiative_status: str = "needs_you", **git: Any
) -> tuple[InitiativeWorld, Initiative, Run]:
    world = InitiativeWorld(git=FakeRemoteGit(refs={"main": HUB_SHA}, **git))
    initiative = world.initiative()
    run = a_live_run(world, initiative, status=initiative_status)
    world.seed(initiative, run)
    return world, initiative, run


def test_the_cancel_is_committed_then_the_run_cancelled_then_the_branch_deleted() -> None:
    world, initiative, run = world_with()

    cancelled = cancel(world, initiative)

    assert cancelled.cancelled_at is not None
    assert cancelled.branch_cleanup_error is None
    assert world.initiatives.initiatives[initiative.id].cancelled_at is not None
    assert world.runs.runs[run.id].status == "cancelled"
    assert deletes(world) == [(world.base_dir, BRANCH)]
    assert world.uow.calls.count("commit") == TWO_COMMITS
    assert [call for call, _ in world.engine.calls][:1] == ["cancel"]


def test_a_failing_delete_is_kept_and_a_second_cancel_clears_it() -> None:
    world, initiative, _ = world_with(
        delete_remote_branch=[GitError(command="push", exit_code=1, output="denied"), True]
    )

    assert cancel(world, initiative).branch_cleanup_error == "denied"
    assert world.initiatives.initiatives[initiative.id].branch_cleanup_error == "denied"

    again = cancel(world, initiative)

    assert again.branch_cleanup_error is None
    assert len(deletes(world)) == TWO_COMMITS


def test_an_already_gone_branch_clears_the_error_too() -> None:
    world, initiative, _ = world_with(
        delete_remote_branch=[GitError(command="p", exit_code=1, output="x")]
    )
    cancel(world, initiative)
    world.git._delete_script = [None]  # the remote no longer holds it: `False`

    assert cancel(world, initiative).branch_cleanup_error is None


def test_a_run_that_does_not_stop_keeps_the_branch_and_names_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, initiative, run = world_with()
    monkeypatch.setattr(use_cases, "handle_signal", lambda *_: None)

    cancelled = cancel(world, initiative)

    assert cancelled.branch_cleanup_error == f"Run {run.id} still stopping"
    assert deletes(world) == []


def test_a_run_that_ended_meanwhile_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    world, initiative, _ = world_with()

    def ended(ports: Any, run_id: Any, signal: Any) -> None:
        world.runs.runs[run_id] = world.runs.runs[run_id].model_copy(update={"status": "done"})
        raise Conflict("run is done")

    monkeypatch.setattr(use_cases, "handle_signal", ended)

    assert cancel(world, initiative).branch_cleanup_error is None
    assert len(deletes(world)) == 1


def test_a_cancelled_initiative_with_nothing_left_is_refused() -> None:
    world = InitiativeWorld()
    initiative = world.initiative(cancelled_at=AT)
    world.seed(initiative, a_live_run(world, initiative, status="cancelled"))

    with pytest.raises(Conflict, match=r"^already cancelled$"):
        cancel(world, initiative)

    assert world.initiatives.calls[-1][0] == "get_for_update"
    assert world.uow.committed is False
    assert deletes(world) == []


def test_a_cancelled_initiative_with_a_live_run_is_retried() -> None:
    world = InitiativeWorld()
    initiative = world.initiative(cancelled_at=AT)
    run = a_live_run(world, initiative)
    world.seed(initiative, run)

    cancelled = cancel(world, initiative)

    assert cancelled.cancelled_at == AT
    assert world.runs.runs[run.id].status == "cancelled"
    assert len(deletes(world)) == 1


def test_a_merged_initiative_is_not_cancelled() -> None:
    world = InitiativeWorld()
    initiative = world.initiative(pr_merged_at=datetime(2026, 1, 1, tzinfo=UTC))
    world.seed(initiative)

    with pytest.raises(Conflict, match=r"^done initiatives are not cancelled$"):
        cancel(world, initiative)

    assert world.uow.committed is False


def test_an_unknown_initiative_is_not_found() -> None:
    world = InitiativeWorld()

    with world.uow, pytest.raises(NotFound):
        cancel_initiative(world.ports, new_id())

    assert world.uow.committed is False


def test_the_initiative_is_locked_before_any_run() -> None:
    world, initiative, _ = world_with()
    log: list[tuple[str, object]] = []
    world.initiatives.calls = log
    world.runs.calls = log

    cancel(world, initiative)

    first_initiative_lock = log.index(("get_for_update", initiative.id))
    run_locks = [
        i
        for i, (call, _) in enumerate(log)
        if call == "get_for_update" and i != first_initiative_lock
    ]
    assert run_locks
    assert first_initiative_lock < min(run_locks)
    assert first_initiative_lock == min(
        i for i, (call, _) in enumerate(log) if call in {"get_for_update", "list_for_initiative"}
    )


def test_a_running_spec_run_is_killed_and_its_worktree_removed_before_the_delete() -> None:
    """Operator answer 2026-11-25 (epic 7 story 3): cancel is the full `handle_signal` cancel."""
    world = InitiativeWorld(git=FakeRemoteGit(refs={"main": HUB_SHA}))
    initiative = world.initiative()
    worktree = Worktree(
        branch=BRANCH, path="/work/wt/spec-snake-v3", created_branch=False, pushed=True
    )
    run = a_live_run(world, initiative, status="running", park_kind=None, worktrees=(worktree,))
    world.seed(initiative, run)
    row = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="steps[0]",
        label="spec",
        kind="conversation",
        gate="deterministic",
        status="running",
    )
    world.signals.writers.steps.add_many([row])
    world.signals.writers.attempts.add(
        Attempt(
            id=new_id(),
            run_id=run.id,
            step_run_id=row.id,
            n=1,
            status="running",
            started_at=AT,
            pgid=4321,
        )
    )

    cancelled = cancel(world, initiative)

    assert world.runs.runs[run.id].status == "cancelled"
    assert [call["pgid"] for call in world.process.called("kill_group")] == [4321]
    names = [call for call, _ in world.git.calls]
    assert [args for call, args in world.git.calls if call == "remove_worktree"] == [
        (world.base_dir, Path(worktree.path))
    ]
    assert names.index("remove_worktree") < names.index("delete_remote_branch")
    assert deletes(world) == [(world.base_dir, BRANCH)]
    assert cancelled.branch_cleanup_error is None
