"""What a blocked agent could still do to a consult's approval, closed (story 1-5 review,
2026-11-02, spine AD-17/AD-22, hard rule 1 as amended).

An approval names its reason or fails closed. The blocked agent's own process group is killed
before the decision path is cleared, so nothing it left running can write there afterwards.
A decision path that is a link, or lies under one, is never read."""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.values import Consult, StepResult
from tests.unit.application.consult_fixtures import DECISION, QUESTION, World, a_consult_world
from tests.unit.application.test_consult_approval_run import approving, with_anchors

AGENT_PGID = 9191


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def fails_closed(world: World, why: str) -> None:
    result = run(world)

    assert result.status == "blocked"
    assert result.reason == f"{QUESTION} · consult failed: {why}"
    assert result.consult == Consult(kind="blocked", question=QUESTION, outcome="failed")


@pytest.mark.parametrize("reason", ["", "  "])
def test_an_approval_with_no_reason_fails_closed(reason: str) -> None:
    world = with_anchors(a_consult_world(decision=approving("[tests/a.py]", reason=reason)))

    fails_closed(world, "approval names no reason")


def test_an_answer_with_no_files_needs_no_reason() -> None:
    world = with_anchors(a_consult_world(decision="---\nstatus: answer\n---\n\nGo on.\n"))

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"


def with_agent_group(world: World, pgid: int | None) -> World:
    previous = world.ctx.previous_attempt
    assert previous is not None
    ctx = replace(world.ctx, previous_attempt=previous.model_copy(update={"pgid": pgid}))
    return replace(world, ctx=ctx)


def test_the_blocked_agents_group_is_killed_before_the_decision_path_is_cleared() -> None:
    world = with_agent_group(
        with_anchors(a_consult_world(decision=approving("[tests/a.py]", reason="AC 2"))),
        AGENT_PGID,
    )
    world.workspace.write(DECISION, "planted")
    at_kill: list[str | None] = []
    world.process.kill_group = lambda pgid: at_kill.append(world.workspace.read(DECISION))  # type: ignore[method-assign]

    run(world)

    assert at_kill == ["planted"]
    assert world.workspace.read(DECISION) is not None


def test_the_kill_names_the_blocked_agents_group() -> None:
    world = with_agent_group(with_anchors(a_consult_world(decision=approving("[]"))), AGENT_PGID)

    run(world)

    kills = world.process.called("kill_group")
    assert kills[0] == {"method": "kill_group", "pgid": AGENT_PGID}


def test_no_group_recorded_kills_nothing_before_the_senior() -> None:
    world = with_agent_group(with_anchors(a_consult_world(decision=approving("[]"))), None)

    run(world)

    assert world.process.called("kill_group") == []


def test_a_planted_link_at_the_decision_path_is_removed_first() -> None:
    world = with_anchors(a_consult_world())
    world.workspace.links.add(DECISION)
    world.workspace.write(DECISION, approving("[tests/a.py]", reason="AC 2"))

    fails_closed(world, "no readable decision")

    assert not world.workspace.is_link(DECISION)


def test_a_decision_path_that_became_a_link_while_the_senior_ran_is_never_read() -> None:
    world = with_anchors(a_consult_world())

    def the_link_appears() -> None:
        world.workspace.write(DECISION, approving("[tests/a.py]", reason="AC 2"))
        world.workspace.links.add(DECISION)

    world.harness.on_wait = the_link_appears

    fails_closed(world, "no readable decision")


def test_a_decision_path_under_a_linked_folder_is_never_read() -> None:
    world = with_anchors(a_consult_world(decision=approving("[tests/a.py]", reason="AC 2")))
    world.workspace.links.add(".orchestrator/consult")

    fails_closed(world, "no readable decision")
