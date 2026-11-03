"""Story 2-1, CAP-8, AD-13's `pause` row: a request, and where it lands.

`pause` writes a flag and a record. `apply_step_result` parks the Run `paused` on the next row
when the row it is finishing would have carried on; `continue` resumes there."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.apply_step_result import (
    apply_step_result,
    budget_second_record,
)
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Consult, Park, Retry, Signal, StepResult
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    PAIR_PLAN,
    World,
    a_world,
    an_attempt,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
COMMIT = "stories[0].commit-guard"
DONE = StepResult(status="done", gate="deterministic")
FIRST_STOP = 1


def running_world(**over: object) -> World:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, **over)
    an_attempt(world, BUILD)
    return world


def pause(world: World) -> None:
    signal_run(world.signal_ports, world.run.id, Signal(kind="pause"))


def finish_build(world: World, result: StepResult = DONE) -> None:
    apply_step_result(
        world.ports,
        world.run.id,
        world.row(BUILD).seq,
        result,
        after_route=lambda run, row, res: budget_second_record(world.ports, run, row, res),
    )


def engine_calls(world: World) -> list[str]:
    return [name for name, _ in world.engine.calls]


# ── the request ──────────────────────────────────────────────────────────────


def test_a_pause_on_a_running_run_records_the_request_and_nothing_else() -> None:
    world = running_world()

    pause(world)

    run = world.stored_run()
    assert (run.status, run.pause_requested) == ("running", True)
    [line] = world.records()
    assert (line.event, line.actor) == ("pause", "operator")
    assert engine_calls(world) == []
    assert world.status_of(BUILD) == "running"


def test_the_use_case_the_router_calls_applies_a_pause_and_refuses_a_second() -> None:
    world = running_world()
    ports = SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir="/work",
        read_environment=lambda _run_id: None,
    )

    handle_signal(ports, world.run.id, Signal(kind="pause"))
    assert world.stored_run().pause_requested

    with pytest.raises(Conflict):
        handle_signal(ports, world.run.id, Signal(kind="pause"))
    assert world.events() == ["pause"]


def test_a_second_pause_is_refused_and_writes_nothing() -> None:
    world = running_world(pause_requested=True)

    with pytest.raises(Conflict):
        pause(world)

    assert world.records() == []


@pytest.mark.parametrize("status", ["queued", "done", "failed", "cancelled"])
def test_a_pause_is_refused_unless_the_run_is_running(status: str) -> None:
    world = a_world(status, EPIC_PLAN, {}, engine_ref={"ref": 1})  # type: ignore[arg-type]

    with pytest.raises(Conflict):
        pause(world)

    assert world.records() == []
    assert not world.stored_run().pause_requested


def test_a_pause_at_a_stop_is_refused() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="why",
    )

    with pytest.raises(Conflict, match="invalid for status needs_you"):
        pause(world)

    assert not world.stored_run().pause_requested


# ── where the pause lands ────────────────────────────────────────────────────


def test_a_finished_row_with_a_request_parks_the_run_on_the_next_row() -> None:
    world = running_world(pause_requested=True)

    finish_build(world)

    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_path) == ("needs_you", "paused", VERIFY)
    assert run.pause_requested is False
    assert run.park_seq == FIRST_STOP
    assert run.park_reason is not None and VERIFY in run.park_reason
    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"
    [line] = world.records()
    assert (line.event, line.actor, line.path) == ("paused", "machine", VERIFY)


def test_the_park_is_on_the_next_row_that_is_not_skipped() -> None:
    world = a_world(
        "running",
        EPIC_PLAN,
        {BUILD: "running", VERIFY: "skipped"},
        pause_requested=True,
    )
    an_attempt(world, BUILD)

    finish_build(world)

    assert world.stored_run().park_path == COMMIT
    assert world.status_of(COMMIT) == "queued"


def test_a_run_without_a_request_carries_on_as_before() -> None:
    world = running_world()

    finish_build(world)

    assert world.stored_run().status == "running"
    assert world.status_of(VERIFY) == "queued"
    assert world.records() == []


def test_a_request_on_the_last_row_ends_the_run_with_no_park() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    world.ports.runs.update(world.run.model_copy(update={"pause_requested": True}))
    an_attempt(world, "checkout")

    apply_step_result(world.ports, world.run.id, 2, DONE)

    run = world.stored_run()
    assert (run.status, run.pause_requested, run.park_kind) == ("done", False, None)
    assert world.events() == ["done"]


def test_a_row_that_parks_by_itself_keeps_its_own_stop_and_clears_the_request() -> None:
    world = running_world(pause_requested=True)
    blocked = StepResult(
        status="blocked",
        gate="liveness",
        reason="intent gap",
        park=Park(kind="blocked", reason="intent gap", path=BUILD),
    )

    finish_build(world, blocked)

    run = world.stored_run()
    assert (run.park_kind, run.park_path, run.pause_requested) == ("blocked", BUILD, False)
    assert world.events() == ["blocked"]


def test_a_budget_stop_over_a_routed_one_clears_the_request_too() -> None:
    world = running_world(pause_requested=True)
    result = StepResult(
        status="blocked",
        gate="liveness",
        reason="intent gap",
        park=Park(kind="blocked", reason="intent gap", path=BUILD),
        budget_park=Park(kind="budget", reason="budget $11.00 / $10.00", path=BUILD),
    )

    finish_build(world, result)

    run = world.stored_run()
    assert (run.park_kind, run.pause_requested) == ("budget", False)


def test_a_failed_run_carries_no_request() -> None:
    world = running_world(pause_requested=True)
    world.ports.steps.update(
        world.row(BUILD).model_copy(update={"with_resolved": {"on_fail": "fail"}})
    )

    finish_build(world, StepResult(status="error", gate="deterministic", reason="exit 1"))

    run = world.stored_run()
    assert (run.status, run.pause_requested) == ("failed", False)


def test_an_errored_row_that_carries_on_lets_the_pause_land() -> None:
    world = running_world(pause_requested=True)
    world.ports.steps.update(
        world.row(BUILD).model_copy(update={"with_resolved": {"on_fail": "continue"}})
    )

    finish_build(world, StepResult(status="error", gate="deterministic", reason="exit 1"))

    run = world.stored_run()
    assert (run.park_kind, run.park_path) == ("paused", VERIFY)


# ── a row that did not finish ────────────────────────────────────────────────


def test_a_consult_requeue_leaves_the_request_standing() -> None:
    world = running_world(pause_requested=True)
    world.ports.steps.update(
        world.row(BUILD).model_copy(
            update={
                "with_resolved": {
                    "consult": {
                        "model": "senior",
                        "harness": "",
                        "skill": "senior-consult",
                        "on": ["blocked"],
                        "timeout_min": None,
                        "prompts": {"dispatch": "d", "answer": "a"},
                    }
                }
            }
        )
    )
    offer = StepResult(
        status="error",
        gate="liveness",
        reason="consult: q",
        consult=Consult(kind="blocked", question="q", snapshot={}),
    )

    finish_build(world, offer)

    run = world.stored_run()
    assert (run.status, run.pause_requested, run.park_kind) == ("running", True, None)
    assert world.status_of(BUILD) == "queued"
    assert world.status_of(VERIFY) == "planned"


def test_a_template_retry_leaves_the_request_standing() -> None:
    world = running_world(pause_requested=True)
    failed = StepResult(
        status="error",
        gate="deterministic",
        reason="exit 1",
        retry=Retry(prompt="again", max=2),
    )

    finish_build(world, failed)

    run = world.stored_run()
    assert (run.status, run.pause_requested) == ("running", True)
    assert world.status_of(BUILD) == "queued"


# ── the stop ─────────────────────────────────────────────────────────────────


def paused_world() -> World:
    world = running_world(pause_requested=True)
    finish_build(world)
    return world


def test_continue_at_a_pause_resumes_the_run_with_the_row_already_queued() -> None:
    world = paused_world()

    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))

    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_path) == ("running", None, None)
    assert world.status_of(VERIFY) == "queued"
    assert engine_calls(world) == ["signal"]
    assert world.events()[-1] == "continue"


def test_continue_naming_the_stop_is_applied_and_a_stale_one_is_refused() -> None:
    world = paused_world()

    with pytest.raises(Conflict, match="stop 0"):
        signal_run(world.signal_ports, world.run.id, Signal(kind="continue", stop=0))
    assert world.stored_run().status == "needs_you"

    signal_run(
        world.signal_ports, world.run.id, Signal(kind="continue", stop=world.stored_run().park_seq)
    )
    assert world.stored_run().status == "running"


@pytest.mark.parametrize(
    "kind",
    [
        "answer",
        "retry",
        "skip_step",
        "skip_story",
        "skip_epic",
        "budget_raise",
        "terminal_start",
        "terminal_resume",
        "pause",
    ],
)
def test_a_paused_run_refuses_every_other_action(kind: str) -> None:
    world = paused_world()
    before = len(world.records())

    with pytest.raises(Conflict):
        signal_run(
            world.signal_ports,
            world.run.id,
            Signal(kind=kind, payload={"budget_usd": "99"}),  # type: ignore[arg-type]
        )

    assert len(world.records()) == before
    assert world.stored_run().status == "needs_you"


def test_cancel_at_a_pause_cancels_the_run_and_skips_the_queued_row() -> None:
    world = paused_world()

    signal_run(world.signal_ports, world.run.id, Signal(kind="cancel"))

    assert world.stored_run().status == "cancelled"
    assert world.status_of(VERIFY) == "skipped"
    assert engine_calls(world) == ["cancel"]


def test_cancel_with_a_request_pending_clears_it() -> None:
    world = running_world(pause_requested=True)

    signal_run(world.signal_ports, world.run.id, Signal(kind="cancel"))

    run = world.stored_run()
    assert (run.status, run.pause_requested) == ("cancelled", False)


def test_a_pause_that_never_landed_cannot_land_after_the_stop_resumes() -> None:
    world = paused_world()
    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))
    world.ports.steps.update(world.row(VERIFY).model_copy(update={"status": "running"}))
    an_attempt(world, VERIFY)

    apply_step_result(world.ports, world.run.id, world.row(VERIFY).seq, DONE)

    assert world.stored_run().status == "running"
    assert world.status_of(COMMIT) == "queued"
