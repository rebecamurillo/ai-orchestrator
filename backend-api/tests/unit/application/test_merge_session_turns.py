"""A merge-conflict step session's turns (epic 8 story 4, AC2, AC7, AC8): the opening skill,
the machine's `continue`, and the sweep that never stages a conflict."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from orchestrator.application.rules import session
from orchestrator.application.use_cases import session_close
from orchestrator.application.use_cases.session_turn import commit_turn
from orchestrator.application.use_cases.signal_apply import SignalPorts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from tests.unit.application.merge_world import AGENT, MERGE, PLAN, SKILL
from tests.unit.application.session_turn_fixtures import TurnWorld, a_result, a_turn_world
from tests.unit.fakes.git import FakeGit

UNMERGED = "UU a.md\n?? notes.md"
UNTRACKED = "?? notes.md"
MODIFIED = " M a.md"
ROW: dict[str, Any] = {"harness": "claude", "model": "claude-sonnet"}


def a_merge_session(git: FakeGit | None = None, *, initiative: bool = True) -> TurnWorld:
    world = a_turn_world(
        git=git,
        results=[a_result(session_id="s-1") for _ in range(3)],
        plan=PLAN,
        park_kind="merge_conflict",
        park_path=MERGE,
        row_status="error",
        park_seq=5,
        senior_session=True,
        start=False,
        **(
            {"initiative_id": new_id(), "initiative_round": 1, "initiative_position": 1}
            if initiative
            else {}
        ),
    )
    inner = world.session.world
    for path, fields in ((MERGE, ROW), (AGENT, {"skill": SKILL})):
        inner.ports.steps.update(inner.row(path).model_copy(update={"with_resolved": dict(fields)}))
    inner.ports.records.add(
        GateRecord(
            id=new_id(),
            run_id=inner.run.id,
            at=inner.clock.now(),
            event="session_start",
            actor="machine",
            payload={"scope": "step", "harness": "claude", "model": "claude-sonnet"},
        )
    )
    return world


def with_signal(world: TurnWorld) -> Any:
    inner = world.session.world
    return replace(world.ports, signal=SignalPorts(writers=inner.ports, engine=inner.engine))


def turn(world: TurnWorld, text: str = "resolve it") -> UUID:
    posted = world.post(text)
    world.run(posted.attempt_id)
    return posted.attempt_id


def continues(world: TurnWorld) -> list[GateRecord]:
    return [r for r in world.session.world.records() if r.event == "continue"]


def names(git: FakeGit) -> list[str]:
    return [name for name, _ in git.calls]


def test_the_first_turn_opens_with_the_skill_of_the_merge_agent_row() -> None:
    world = a_merge_session()

    turn(world)

    opening = world.harness.called("start")[0]["prompt"]
    assert opening.startswith(f"{SKILL} ")


def test_with_no_agent_row_the_first_turn_opens_with_the_senior_skill() -> None:
    world = a_merge_session()
    world.session.world.ports.steps.update(
        world.session.world.row(AGENT).model_copy(update={"kind": "shell"})
    )

    turn(world)

    assert world.harness.called("start")[0]["prompt"].startswith(f"{session.OPENING_SKILL} ")


def test_a_done_turn_with_no_unmerged_path_sends_one_machine_continue() -> None:
    world = a_merge_session(FakeGit(status=[UNTRACKED]))
    attempt = turn(world)

    commit_turn(with_signal(world), attempt)

    (sent,) = continues(world)
    assert (sent.actor, sent.text) == ("machine", "merge resumed after the agent's turn")
    assert world.session.world.stored_run().senior_session is False
    assert world.session.world.stored_run().status == "running"


def test_a_turn_that_leaves_an_unmerged_path_sends_nothing() -> None:
    world = a_merge_session(FakeGit(status=[UNMERGED]))
    attempt = turn(world)

    commit_turn(with_signal(world), attempt)

    assert continues(world) == []
    assert world.session.world.stored_run().senior_session is True


def test_an_errored_turn_sends_nothing() -> None:
    world = a_merge_session(FakeGit(status=[UNTRACKED]))
    world.harness.results = [a_result(exit_code=1)]
    attempt = turn(world)

    commit_turn(with_signal(world), attempt)

    assert continues(world) == []


def test_a_signal_the_run_refuses_is_logged_and_not_raised() -> None:
    world = a_merge_session(FakeGit(status=[UNTRACKED]))
    attempt = turn(world)
    world.session.turn(n=9, status="queued", ended_at=None)

    commit_turn(with_signal(world), attempt)

    assert continues(world) == []
    assert world.session.world.stored_run().senior_session is True


def test_a_turn_with_no_signal_wiring_sends_nothing() -> None:
    world = a_merge_session(FakeGit(status=[UNTRACKED]))
    attempt = turn(world)

    commit_turn(world.ports, attempt)

    assert continues(world) == []


def test_no_stage_or_commit_while_a_path_is_unmerged() -> None:
    world = a_merge_session(FakeGit(status=[UNMERGED]))
    attempt = turn(world)
    world.commit(attempt)

    assert not {"stage", "commit"} & set(names(world.git))


def test_a_tree_with_no_unmerged_path_is_swept_and_committed() -> None:
    world = a_merge_session(FakeGit(status=[MODIFIED]))
    attempt = turn(world)
    world.commit(attempt)

    assert "stage" in names(world.git)
    assert "commit" in names(world.git)


def test_a_run_without_an_initiative_never_asks_about_unmerged_paths() -> None:
    world = a_merge_session(FakeGit(status=[UNMERGED]), initiative=False)
    world.session.world.ports.runs.update(
        world.session.world.stored_run().model_copy(update={"park_kind": "blocked"})
    )
    attempt = turn(world)

    commit_turn(with_signal(world), attempt)

    assert continues(world) == []


def test_after_turn_for_an_attempt_that_is_gone_does_nothing() -> None:
    world = a_merge_session()

    session_close.after_turn(world.ports, new_id())

    assert continues(world) == []
