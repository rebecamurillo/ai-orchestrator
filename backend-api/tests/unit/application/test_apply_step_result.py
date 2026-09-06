"""`apply_step_result` — every completion transition of AD-8, over the shipped plan shapes."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from orchestrator.application.use_cases.apply_step_result import (
    LATE_RESULT,
    apply_step_result,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import InvalidTransition
from orchestrator.domain.values import Park, Redispatch, StepResult
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    PAIR_PLAN,
    World,
    a_world,
    an_attempt,
)

DONE = StepResult(status="done", gate="deterministic", output_ref="/work/logs/1.log")


def a_pair(**over: object) -> World:
    return a_world("running", PAIR_PLAN, {"plan": "running"}, **over)


# ── AC2: a finished row queues its successor, and the last one ends the Run ──


def test_a_done_row_queues_its_successor_and_leaves_the_run_alone() -> None:
    world = a_pair()

    apply_step_result(world.ports, world.run.id, 1, DONE)

    assert world.status_of("plan") == "done"
    assert world.status_of("checkout") == "queued"
    assert world.stored_run().status == "running"
    assert world.events() == []


def test_the_last_row_ending_done_ends_the_run_with_the_done_record() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})

    apply_step_result(world.ports, world.run.id, 2, DONE)

    stored = world.stored_run()
    assert stored.status == "done"
    assert stored.ended_at == world.clock.now()
    assert world.events() == ["done"]


def test_the_successor_walk_reads_through_planner_skipped_rows() -> None:
    """`epic@1` over an already-done Story ends in four `skipped` rows (AD-8: "done or skipped")."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {
            "stories[1].after": "running",
            "push": "skipped",
            "link": "skipped",
        },
    )

    apply_step_result(world.ports, world.run.id, 12, DONE)

    assert world.stored_run().status == "done"


def test_the_walk_queues_the_first_planned_row_past_the_skipped_ones() -> None:
    world = a_world(
        "running",
        EPIC_PLAN,
        {"stories[0].commit-guard": "running", "stories[1].sync": "skipped"},
    )

    apply_step_result(world.ports, world.run.id, 7, DONE)

    assert world.status_of("stories[1].build") == "queued"


def test_the_walk_writes_nothing_when_the_next_live_row_is_already_past_planned() -> None:
    """After a redispatch the rows between target and current keep their statuses (AD-9)."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {"stories[0].build": "running", "stories[0].verify": "error"},
    )

    apply_step_result(world.ports, world.run.id, 5, DONE)

    assert world.status_of("stories[0].verify") == "error"
    assert world.stored_run().status == "running"


def test_a_skipped_result_also_moves_the_successor_on() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "queued"})

    skipped = StepResult(status="skipped", gate="unvalidated")

    apply_step_result(world.ports, world.run.id, 1, skipped)

    assert world.status_of("plan") == "skipped"
    assert world.status_of("checkout") == "queued"


# ── the Attempt's finish half ────────────────────────────────────────────────


def test_the_latest_attempt_is_closed_with_the_status_the_row_reached() -> None:
    world = a_pair()
    an_attempt(world, "plan")

    world.clock.advance(30)
    apply_step_result(world.ports, world.run.id, 1, DONE)

    attempt = world.attempts_of("plan")[0]
    assert (attempt.status, attempt.output_ref) == ("done", "/work/logs/1.log")
    assert attempt.ended_at == world.clock.now()


def test_a_row_with_no_attempt_at_all_still_applies() -> None:
    """A planner-skipped row never ran, so there is no attempt to close."""
    world = a_pair()

    apply_step_result(world.ports, world.run.id, 1, DONE)

    assert world.attempts_of("plan") == []


# ── AC3: a park stops the Run ────────────────────────────────────────────────


def test_a_park_writes_the_three_fields_and_one_record_together() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "running"})
    park = Park(kind="plan_stale", reason="plan stale: stories.yaml")

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(status="error", gate="deterministic", park=park, reason=park.reason),
    )

    stored = world.stored_run()
    assert world.status_of("plan") == "error"
    assert stored.status == "needs_you"
    assert (stored.park_kind, stored.park_path, stored.park_reason) == (
        "plan_stale",
        "plan",
        "plan stale: stories.yaml",
    )
    assert world.events() == ["plan_stale"]


def test_the_park_record_names_the_row_the_attempt_and_the_reason() -> None:
    world = a_world("running", EPIC_PLAN, {"stories[0].build": "running"})
    an_attempt(world, "stories[0].build", n=2)
    park = Park(kind="blocked", reason="needs a decision on the adapter")

    apply_step_result(
        world.ports,
        world.run.id,
        5,
        StepResult(status="blocked", gate="liveness", park=park, reason=park.reason),
    )

    line = world.records()[0]
    assert (line.event, line.actor, line.path, line.attempt_n) == (
        "blocked",
        "machine",
        "stories[0].build",
        2,
    )
    assert line.text == "needs a decision on the adapter"


def test_a_park_that_names_its_own_path_keeps_it() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "running"})
    park = Park(kind="internal", reason="internal: KeyError", path="somewhere/else")

    apply_step_result(
        world.ports, world.run.id, 1, StepResult(status="error", gate="deterministic", park=park)
    )

    assert world.stored_run().park_path == "somewhere/else"


# ── AC4: the bounded redispatch ──────────────────────────────────────────────


def a_verify_world(count: int = 0, target_status: str = "done") -> World:
    world = a_world(
        "running",
        EPIC_PLAN,
        {"stories[0].build": target_status, "stories[0].verify": "running"},
    )
    build = world.row("stories[0].build")
    world.ports.steps.update(build.model_copy(update={"redispatch_count": count}))
    return world


def a_verify_failure() -> StepResult:
    return StepResult(
        status="error",
        gate="deterministic",
        redispatch=Redispatch(target_seq=5, max=1),
        reason="verify failed",
    )


def test_a_redispatch_under_the_bound_queues_the_target_and_counts_it() -> None:
    world = a_verify_world()

    apply_step_result(world.ports, world.run.id, 6, a_verify_failure())

    build = world.row("stories[0].build")
    assert (build.status, build.redispatch_count) == ("queued", 1)
    assert world.stored_run().status == "running"


def test_the_redispatch_record_counts_the_dispatch_out_of_the_bound() -> None:
    world = a_verify_world()
    an_attempt(world, "stories[0].verify")

    apply_step_result(world.ports, world.run.id, 6, a_verify_failure())

    line = world.records()[0]
    assert (line.event, line.actor, line.attempt_n) == ("redispatch", "machine", 1)
    assert line.text == "verify failed, story re-dispatched 1/1"


def test_the_rows_between_the_target_and_the_current_one_are_left_as_they_are() -> None:
    world = a_verify_world()

    apply_step_result(world.ports, world.run.id, 6, a_verify_failure())

    assert world.status_of("stories[0].verify") == "error"
    assert world.status_of("stories[0].commit-guard") == "planned"


def test_the_bound_being_used_up_parks_the_run_instead() -> None:
    world = a_verify_world(count=1)

    apply_step_result(world.ports, world.run.id, 6, a_verify_failure())

    stored = world.stored_run()
    assert (stored.status, stored.park_kind, stored.park_reason) == (
        "needs_you",
        "verify_failed",
        "verify failed 2/2",
    )
    assert world.row("stories[0].build").redispatch_count == 1


def test_a_redispatch_onto_a_row_that_was_never_run_parks_with_the_skip_reason() -> None:
    world = a_verify_world(target_status="skipped")

    apply_step_result(world.ports, world.run.id, 6, a_verify_failure())

    assert world.stored_run().park_reason == "re-baseline failed after skip"


def test_a_redispatch_decides_the_routing_even_when_the_result_also_carries_a_park() -> None:
    """The brief routes the redispatch first (c) and only then reads `result.park` (d)."""
    world = a_verify_world()
    both = a_verify_failure().model_copy(
        update={"park": Park(kind="internal", reason="internal: KeyError")}
    )

    apply_step_result(world.ports, world.run.id, 6, both)

    assert world.status_of("stories[0].build") == "queued"
    assert world.stored_run().status == "running"
    assert world.events() == ["redispatch"]


def test_a_redispatch_naming_a_seq_the_plan_does_not_have_is_a_not_found() -> None:
    world = a_verify_world()
    missing = StepResult(
        status="error", gate="deterministic", redispatch=Redispatch(target_seq=99, max=1)
    )

    with pytest.raises(NotFound):
        apply_step_result(world.ports, world.run.id, 6, missing)


# ── on_fail: fail ────────────────────────────────────────────────────────────


def test_an_error_on_a_row_whose_template_said_fail_ends_the_run() -> None:
    world = a_world(
        "running",
        EPIC_PLAN,
        {"baseline": "running"},
        with_resolved={"baseline": {"on_fail": "fail"}},
    )

    apply_step_result(
        world.ports,
        world.run.id,
        3,
        StepResult(status="error", gate="deterministic", reason="baseline exit 1"),
    )

    stored = world.stored_run()
    assert (stored.status, stored.ended_at) == ("failed", world.clock.now())
    line = world.records()[0]
    assert (line.event, line.text, line.path) == ("failed", "baseline exit 1", "baseline")


def test_an_error_on_a_row_that_escalates_leaves_the_run_running_for_its_park() -> None:
    """`escalate` is the DSL default: the executor's own `Park` is what stops the Run."""
    world = a_world("running", EPIC_PLAN, {"baseline": "running"})

    apply_step_result(
        world.ports, world.run.id, 3, StepResult(status="error", gate="deterministic")
    )

    assert world.stored_run().status == "running"


def test_a_blocked_row_without_a_park_moves_nothing_but_the_row() -> None:
    world = a_world("running", EPIC_PLAN, {"stories[0].build": "running"})

    apply_step_result(world.ports, world.run.id, 5, StepResult(status="blocked", gate="liveness"))

    assert world.status_of("stories[0].build") == "blocked"
    assert world.stored_run().status == "running"


# ── AC6: a late result ───────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["cancelled", "failed", "needs_you"])
def test_a_result_for_a_run_that_is_not_running_writes_nothing(status: str) -> None:
    world = a_world(status, PAIR_PLAN, {"plan": "running"})  # type: ignore[arg-type]

    with capture_logs() as lines:
        apply_step_result(world.ports, world.run.id, 1, DONE)

    assert world.status_of("plan") == "running"
    assert not world.ports.uow.committed
    assert [line["event"] for line in lines] == [LATE_RESULT]


# ── the refusals and the seam ────────────────────────────────────────────────


def test_a_result_for_a_run_that_is_not_stored_is_a_not_found() -> None:
    world = a_pair()

    with pytest.raises(NotFound):
        apply_step_result(world.ports, new_id(), 1, DONE)


def test_a_result_for_a_seq_the_plan_does_not_have_is_a_not_found() -> None:
    world = a_pair()

    with pytest.raises(NotFound):
        apply_step_result(world.ports, world.run.id, 99, DONE)


def test_a_result_reporting_a_status_that_is_not_a_completion_raises() -> None:
    world = a_pair()

    with pytest.raises(InvalidTransition) as raised:
        apply_step_result(world.ports, world.run.id, 1, StepResult(status="queued", gate="human"))

    assert "queued" in str(raised.value)


def test_the_epic_5_seam_is_called_with_the_run_as_it_now_stands() -> None:
    world = a_pair()
    seen: list[tuple[Run, StepRun, StepResult]] = []

    apply_step_result(
        world.ports, world.run.id, 1, DONE, after_route=lambda *args: seen.append(args)
    )

    run, row, result = seen[0]
    assert (run.status, row.status, result) == ("running", "done", DONE)


def test_the_whole_result_is_one_committed_unit_of_work() -> None:
    world = a_pair()

    apply_step_result(world.ports, world.run.id, 1, DONE)

    assert world.ports.uow.calls == ["enter", "commit", "exit"]
