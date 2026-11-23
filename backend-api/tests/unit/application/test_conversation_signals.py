"""The conversation stop's signals (epic 4 story 1): `step_close`, the forced skip, the gate."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.rules import signals_conversation, signals_table
from orchestrator.application.rules.chat_close import VERBS
from orchestrator.application.rules.signals import admitted_signals
from orchestrator.application.use_cases import conversation_effects
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import CHK_PARK_KINDS, StepStatus
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import World, a_world

STOP = 3
PLAN = (("plan", "plan.check"), ("talk", "conversation"), ("after", "shell"))
WALK_PLAN = (
    ("epics[0].stories[0].spec", "agent"),
    ("epics[0].stories[0].gate", "checkpoint"),
    ("epics[0].stories[0].build", "agent"),
    ("epics[0].push", "git.push"),
)


def parked(
    park_kind: str = "conversation",
    plan: tuple[tuple[str, str], ...] = PLAN,
    path: str = "talk",
    status: StepStatus = "checkpoint",
    role: str = "",
    **over: Any,
) -> World:
    statuses: dict[str, StepStatus] = {row: "done" for row, _ in plan[: _index(plan, path)]}
    statuses[path] = status
    world = a_world(
        "needs_you",
        plan,
        statuses,
        park_kind=park_kind,
        park_path=path,
        park_reason="r",
        park_seq=STOP,
        **over,
    )
    if role:
        row = world.row(path)
        world.ports.steps.update(row.model_copy(update={"role": role}))
    return world


def _index(plan: tuple[tuple[str, str], ...], path: str) -> int:
    return [p for p, _ in plan].index(path)


def send(world: World, kind: Any, stop: int | None = STOP, **payload: Any) -> None:
    signal_run(world.signal_ports, world.run.id, Signal(kind=kind, payload=payload, stop=stop))


def test_step_close_queues_the_row_and_resumes_the_run() -> None:
    world = parked()

    send(world, "step_close")

    run = world.stored_run()
    assert world.status_of("talk") == "queued"
    assert (run.status, run.senior_session) == ("running", False)
    record = world.records()[-1]
    assert (record.event, record.text, record.actor) == ("step_close", "step closed", "machine")


def test_step_close_without_its_stop_is_refused_and_writes_nothing() -> None:
    world = parked()
    before = world.records()

    with pytest.raises(Conflict, match="step_close needs the stop it answers"):
        send(world, "step_close", stop=None)

    assert world.records() == before
    assert world.status_of("talk") == "checkpoint"


def test_step_close_with_a_stale_stop_is_refused_and_writes_nothing() -> None:
    world = parked()

    with pytest.raises(Conflict):
        send(world, "step_close", stop=2)

    assert world.records() == []
    assert world.stored_run().status == "needs_you"


@pytest.mark.parametrize("payload", [{}, {"forced": False}, {"forced": "true"}, {"forced": 1}])
def test_a_plain_skip_step_is_refused_on_a_conversation_stop(payload: dict[str, Any]) -> None:
    world = parked()

    with pytest.raises(Conflict, match="invalid for status needs_you / park conversation"):
        send(world, "skip_step", **payload)

    assert world.status_of("talk") == "checkpoint"


def test_a_forced_skip_without_its_stop_is_refused() -> None:
    with pytest.raises(Conflict, match="invalid for status"):
        send(parked(), "skip_step", stop=None, forced=True)


def test_a_forced_skip_step_skips_the_row_and_resumes() -> None:
    world = parked()

    send(world, "skip_step", forced=True)

    assert world.status_of("talk") == "skipped"
    assert world.row("talk").reason == "skipped, forced"
    assert world.status_of("after") == "queued"
    assert world.stored_run().status == "running"
    assert world.records()[-1].text == "skipped, forced"


def test_an_ordinary_skip_keeps_its_own_reason_and_text() -> None:
    world = parked("blocked", PLAN, "talk", "blocked")

    send(world, "skip_step")

    assert world.row("talk").reason == "skipped by operator"
    assert world.records()[-1].text == "step skipped by the operator"


@pytest.mark.parametrize("kind", ["skip_story", "skip_epic"])
def test_a_conversation_stop_admits_no_wider_skip(kind: str) -> None:
    world = parked(plan=WALK_PLAN, path="epics[0].stories[0].gate")

    with pytest.raises(Conflict, match="invalid for status"):
        send(world, kind, forced=True)


@pytest.mark.parametrize("park_kind", ["blocked", "conversation"])
@pytest.mark.parametrize("kind", ["skip_step", "skip_story", "skip_epic"])
@pytest.mark.parametrize("forced", [False, True])
def test_no_skip_is_admitted_on_an_interactive_spec_gate(
    park_kind: str, kind: str, forced: bool
) -> None:
    status: StepStatus = "checkpoint" if park_kind == "conversation" else "blocked"
    world = parked(
        park_kind,
        WALK_PLAN,
        "epics[0].stories[0].gate",
        status,
        role="spec-gate",
        lane="interactive",
    )
    payload = {"forced": True} if forced else {}

    with pytest.raises(Conflict, match="invalid for status"):
        send(world, kind, **payload)

    assert world.stored_run().status == "needs_you"
    assert world.records() == []


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("skip_step", "step skipped by the operator"),
        ("skip_story", "story skipped by the operator"),
        ("skip_epic", "epic skipped by the operator"),
    ],
)
def test_a_walk_run_keeps_its_skips_on_a_spec_gate_row(kind: str, text: str) -> None:
    world = parked(
        "blocked", WALK_PLAN, "epics[0].stories[0].gate", "blocked", role="spec-gate", lane="walk"
    )

    send(world, kind)

    assert world.records()[-1].text == text
    assert world.stored_run().status == "running"
    if kind == "skip_step":
        assert world.row("epics[0].stories[0].gate").reason == "skipped by operator"


def test_a_conversation_stop_offers_cancel_only() -> None:
    assert admitted_signals("conversation", "conversation") == ("cancel",)
    assert admitted_signals("conversation", "agent") == ("cancel",)


def test_the_conversation_names_are_wired() -> None:
    assert VERBS["step_close"] == "step closed"
    assert "conversation" in CHK_PARK_KINDS
    assert signals_table.VALID["step_close"] is signals_conversation.STEP_CLOSE
    assert signals_conversation.is_forced(Signal(kind="skip_step", payload={"forced": True}))
    assert conversation_effects.SKIPPED_FORCED == "skipped, forced"


def test_the_spec_gate_lock_reads_the_lane_and_the_role() -> None:
    world = parked(role="spec-gate", lane="interactive")
    run, row = world.stored_run(), world.row("talk")

    assert signals_conversation.gate_locked(run, row)
    assert not signals_conversation.gate_locked(run, None)
    assert not signals_conversation.gate_locked(run.model_copy(update={"lane": "walk"}), row)
