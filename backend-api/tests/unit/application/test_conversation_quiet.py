"""A conversation stop is announced nowhere and posted to no chat (epic 4 story 1)."""

from __future__ import annotations

from orchestrator.application.jobs.chat_post import due_kind
from orchestrator.application.use_cases.writers import set_run
from tests.unit.application.test_announce import announced
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world, build_run


def test_a_conversation_stop_is_not_announced() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    notifier = announced(world)

    set_run(world.ports, world.run, status="needs_you", park_kind="conversation")

    assert notifier.events == []


def test_another_stop_still_is() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    notifier = announced(world)

    set_run(world.ports, world.run, status="needs_you", park_kind="blocked")

    assert [e.park_kind for e in notifier.events] == ["blocked"]


def test_a_conversation_stop_is_never_due_for_chat() -> None:
    run = build_run("needs_you", park_kind="conversation", park_path="talk", park_reason="r")

    assert due_kind(run) is None
    assert due_kind(run.model_copy(update={"park_kind": "blocked"})) == "blocked"
