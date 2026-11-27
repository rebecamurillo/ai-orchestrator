"""`reopen_initiative` (epic 9 story 2, AC1-AC5, AC7, AC8), on the shared fakes."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases import initiative_reopen
from orchestrator.application.use_cases.advance_retry import (
    AdvanceRetryPorts,
    retry_budget_advances,
)
from orchestrator.application.use_cases.initiative_advance import advance_initiative
from orchestrator.application.use_cases.initiative_reopen import reopen_initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from tests.unit.application.initiative_transition_world import (
    MAIN_SHA,
    SLUG,
    SPEC_BUDGET,
    TransitionWorld,
)

BRANCH = f"spec/{SLUG}"
ROUND_TWO = 2
ROUND_THREE = 3


def reopen(world: TransitionWorld, step: str = "tech", reason: str = "agent exited 1") -> Run:
    with world.uow:
        return reopen_initiative(world.ports, world.initiative_row.id, step, reason)


def conversation_row(world: TransitionWorld, run: Run, step: str, status: str, seq: int) -> None:
    world.signals.writers.steps.add_many(
        [
            StepRun(
                id=new_id(),
                run_id=run.id,
                seq=seq,
                path=f"steps[{seq}]",
                label=step,
                kind="conversation",
                gate="human",
                status=status,  # type: ignore[arg-type]
                with_resolved={"step": step},
            )
        ]
    )


def parked_spec(world: TransitionWorld, **fields: Any) -> Run:
    fields = {"status": "needs_you", "park_kind": "conversation", **fields}
    return world.ended_run(0, **fields)


def cancels(world: TransitionWorld) -> list[dict[str, Any]]:
    return [
        r.payload for r in world.signals.writers.records.records.values() if r.event == "cancel"
    ]


def creations(world: TransitionWorld) -> list[Any]:
    return [args for call, args in world.remote.calls if call == "create_remote_branch"]


def new_runs(world: TransitionWorld, before: set[Any]) -> list[Run]:
    return [r for r in world.runs.runs.values() if r.id not in before]


def test_a_parked_spec_run_is_cancelled_and_round_two_starts_on_the_attached_branch() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    old = parked_spec(world)

    run = reopen(world, "tech", "agent exited 1")

    assert world.runs.runs[old.id].status == "cancelled"
    assert cancels(world) == [{"reason": "reopen", "step": "tech", "branch": "attached"}]
    assert world.initiatives.initiatives[world.initiative_row.id].round == ROUND_TWO
    assert (run.template_name, run.template_version) == ("fx.spec", 1)
    assert (run.initiative_round, run.initiative_position) == (ROUND_TWO, 0)
    assert run.inputs["round_steps"] == "tech"
    assert run.inputs["first_turn"] == "agent exited 1"
    assert run.inputs["branch"] == BRANCH
    assert run.inputs["slug"] == SLUG
    assert creations(world) == []


def test_round_steps_skip_what_is_done_in_any_run_of_the_initiative() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    earlier = world.ended_run(0, status="failed")
    for seq, step in enumerate(("intake", "product"), start=1):
        conversation_row(world, earlier, step, "done", seq)
    conversation_row(world, earlier, "ux", "error", 3)

    assert reopen(world, "ux").inputs["round_steps"] == "ux,tech"

    other = world.ended_run(0, status="done", round_=ROUND_THREE + 2)
    conversation_row(world, other, "tech", "done", 1)
    assert reopen(world, "ux").inputs["round_steps"] == "ux"


def test_a_forced_skip_is_not_done() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    earlier = world.ended_run(0, status="failed")
    conversation_row(world, earlier, "ux", "skipped", 1)
    conversation_row(world, earlier, "tech", "done", 2)

    assert reopen(world, "product").inputs["round_steps"] == "product,ux"


def test_an_absent_branch_is_created_from_the_default_tip_before_the_run() -> None:
    world = TransitionWorld()
    parked_spec(world)

    run = reopen(world)

    assert creations(world) == [(world.base_dir, BRANCH, MAIN_SHA)]
    assert cancels(world)[0]["branch"] == "created"
    assert run.inputs["branch"] == BRANCH


def test_a_blocked_build_is_cancelled_and_the_spec_step_reopens() -> None:
    world = TransitionWorld()
    build = world.ended_run(2, status="needs_you", park_kind="blocked")
    spec = world.ended_run(0)
    for seq, step in enumerate(("intake", "product", "ux", "tech"), start=1):
        conversation_row(world, spec, step, "done", seq)

    run = reopen(world, "tech", "build stopped: x")

    assert world.runs.runs[build.id].status == "cancelled"
    assert cancels(world) == [{"reason": "reopen", "step": "tech", "branch": "created"}]
    assert creations(world) == [(world.base_dir, BRANCH, MAIN_SHA)]
    assert run.inputs["round_steps"] == "tech"
    assert run.budget_usd == SPEC_BUDGET


def test_only_terminal_runs_send_no_signal_and_still_create_the_run() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    world.ended_run(0, status="failed")

    run = reopen(world)

    assert cancels(world) == []
    assert [call for call, _ in world.engine.calls if call == "cancel"] == []
    assert run.initiative_round == ROUND_TWO


def test_the_budget_falls_back_to_the_project_defaults_without_a_run_at_the_entry() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)

    run = reopen(world)

    assert run.budget_usd == world.project.default_budget_usd


@pytest.mark.parametrize(
    ("step", "reason", "error"),
    [("deploy", "why", Invalid), ("gate", "why", Invalid), ("tech", "  ", Invalid)],
)
def test_a_refusal_writes_nothing(step: str, reason: str, error: type[Exception]) -> None:
    world = TransitionWorld()
    live = parked_spec(world)

    with pytest.raises(error):
        reopen(world, step, reason)

    assert world.runs.runs[live.id].status == "needs_you"
    assert len(world.runs.runs) == 1
    assert ("update", world.initiative_row.id) not in world.initiatives.calls
    assert world.remote.calls == []


@pytest.mark.parametrize("closed", ["cancelled_at", "pr_merged_at"])
def test_a_closed_initiative_conflicts_and_writes_nothing(closed: str) -> None:
    world = TransitionWorld()
    live = parked_spec(world)
    world.initiatives.initiatives[world.initiative_row.id] = world.initiative_row.model_copy(
        update={closed: world.harness.clock.now()}
    )

    with pytest.raises(Conflict, match="nothing reopens"):
        reopen(world)

    assert world.runs.runs[live.id].status == "needs_you"
    assert world.remote.calls == []
    assert ("update", world.initiative_row.id) not in world.initiatives.calls


def test_an_unknown_initiative_is_not_found() -> None:
    world = TransitionWorld()

    with world.uow, pytest.raises(NotFound):
        reopen_initiative(world.ports, new_id(), "tech", "why")


def test_a_second_reopen_locks_first_cancels_the_first_run_and_makes_round_three() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    parked_spec(world)

    seeded = len(world.initiatives.calls)
    first = reopen(world)
    world.runs.runs[first.id] = first.model_copy(
        update={"status": "needs_you", "park_kind": "conversation"}
    )
    second = reopen(world)

    assert world.runs.runs[first.id].status == "cancelled"
    assert (first.initiative_round, second.initiative_round) == (ROUND_TWO, ROUND_THREE)
    keys = [(r.initiative_round, r.initiative_position) for r in world.runs.runs.values()]
    assert len(keys) == len(set(keys))
    calls = [c for c, _ in world.initiatives.calls[seeded:]]
    assert calls[0] == "get_for_update"
    assert calls.count("get_for_update") == ROUND_TWO * 2


def test_the_cancelled_runs_advance_starts_no_run() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    old = parked_spec(world)
    advance = world.advance_of(old)

    reopen(world)
    before = set(world.runs.runs)
    advance_initiative(world.advance_ports(), advance.id)

    assert set(world.runs.runs) == before


def test_every_unconsumed_advance_is_consumed_in_the_reopen_and_a_default_starts_no_build() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    done = world.ended_run(1)
    advance = world.advance_of(done)
    world.advances.update(advance.model_copy(update={"blocked_reason": "no project budget"}))
    spent = world.advance_of(world.ended_run(0))
    stamp = world.harness.clock.now()
    world.advances.update(spent.model_copy(update={"consumed_at": stamp}))

    reopen(world)

    assert world.advances.get(spent.id).consumed_at == stamp  # type: ignore[union-attr]

    stored = world.advances.list_for_initiative(world.initiative_row.id)
    assert all(a.consumed_at is not None for a in stored)
    before = set(world.runs.runs)
    cleared = retry_budget_advances(
        AdvanceRetryPorts(world.initiatives, world.advances, world.uow, world.engine),
        world.project.id,
    )
    assert cleared == []
    assert set(world.runs.runs) == before


def test_a_missing_hub_is_not_found_and_writes_nothing() -> None:
    world = TransitionWorld()
    live = parked_spec(world)
    world.initiatives.initiatives[world.initiative_row.id] = world.initiative_row.model_copy(
        update={"repository_id": new_id()}
    )

    with pytest.raises(NotFound):
        reopen(world)

    assert world.runs.runs[live.id].status == "needs_you"


def test_a_run_that_ended_by_itself_meanwhile_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    old = parked_spec(world)

    def refuse(*_: Any) -> None:
        world.runs.runs[old.id] = world.runs.runs[old.id].model_copy(update={"status": "failed"})
        raise Conflict("already ended")

    monkeypatch.setattr(initiative_reopen, "handle_signal", refuse)

    assert reopen(world).initiative_round == ROUND_TWO


def test_a_run_still_live_after_the_cancels_conflicts_and_stores_no_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    old = parked_spec(world)

    def refuse(*_: Any) -> None:
        raise Conflict("signal cancel invalid")

    monkeypatch.setattr(initiative_reopen, "handle_signal", refuse)

    with pytest.raises(Conflict, match=str(old.id)):
        reopen(world)

    assert list(world.runs.runs) == [old.id]
    assert world.initiatives.initiatives[world.initiative_row.id].round == 1


def test_a_default_branch_missing_from_the_hub_is_a_conflict() -> None:
    world = TransitionWorld()
    assert world.remote.refs is not None
    del world.remote.refs["main"]

    with pytest.raises(Conflict, match="main"):
        reopen(world)

    assert creations(world) == []


def test_an_existing_base_clone_is_fetched_not_cloned() -> None:
    world = TransitionWorld(scripts={"base_exists": [True]})

    reopen(world)

    calls = [call for call, _ in world.remote.calls]
    assert "clone_base" not in calls
    assert "fetch_base" in calls


def test_a_failing_branch_create_raises_and_stores_no_run() -> None:
    error = GitError(command="push", exit_code=1, output="denied")
    world = TransitionWorld(scripts={"create_remote_branch": [error]})
    parked_spec(world)

    with pytest.raises(GitError):
        reopen(world)

    assert len(world.runs.runs) == 1
    assert world.initiatives.initiatives[world.initiative_row.id].round == 1
