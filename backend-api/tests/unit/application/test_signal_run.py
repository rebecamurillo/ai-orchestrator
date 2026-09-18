"""`signal_run` — AD-13's table applied, row by row, valid and invalid.

Each test names one row of the table and asserts exactly what that row lists: the rows that
move, the Run fields that change, the gate record, and whether the engine was told. The
plans are the shipped shapes (`writer_fixtures`), so a frame rule is exercised against the
paths `epic@1` and `initiative@1` really produce.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.use_cases.signal_effects import (
    SKIP_MESSAGE,
    SKIPPED_BY_OPERATOR,
    CancelPlan,
)
from orchestrator.application.use_cases.signal_run import SignalOutcome, signal_run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import StepStatus
from orchestrator.domain.values import Signal, Worktree
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    World,
    a_world,
    an_attempt,
)

BUILD = "stories[0].build"
AFTER = "stories[1].after"


def parked(
    park_kind: str,
    park_path: str,
    row_status: StepStatus,
    plan: tuple[tuple[str, str], ...] = EPIC_PLAN,
    statuses: dict[str, StepStatus] | None = None,
    **over: object,
) -> World:
    """A Run stopped for the Operator on one row, the way `apply_step_result` leaves it."""
    rows: dict[str, StepStatus] = {park_path: row_status}
    rows.update(statuses or {})
    return a_world(
        "needs_you",
        plan,
        rows,
        park_kind=park_kind,
        park_path=park_path,
        park_reason="why it stopped",
        **over,
    )


def send(world: World, kind: str, **payload: object) -> SignalOutcome:
    return signal_run(world.signal_ports, world.run.id, Signal(kind=kind, payload=payload))


def engine_calls(world: World) -> list[str]:
    return [name for name, _ in world.engine.calls]


# ── answer ───────────────────────────────────────────────────────────────────


def test_an_answer_re_queues_the_blocked_story_and_resumes_the_run() -> None:
    world = parked("blocked", BUILD, "blocked")

    outcome = send(world, "answer", text="use the psycopg adapter")

    assert world.status_of(BUILD) == "queued"
    assert outcome.run.status == "running"
    assert outcome.resumed
    assert engine_calls(world) == ["signal"]


def test_the_answer_record_is_the_operators_own_words_at_the_parked_row() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "answer", text="use the psycopg adapter")

    line = world.records()[0]
    assert (line.event, line.actor, line.path) == ("answer", "operator", BUILD)
    assert line.text == "use the psycopg adapter"
    assert line.payload == {"text": "use the psycopg adapter"}


def test_resuming_clears_the_three_park_fields_together() -> None:
    world = parked("blocked", BUILD, "blocked")

    stored = send(world, "answer", text="go on").run

    assert (stored.park_kind, stored.park_path, stored.park_reason) == (None, None, None)


def test_a_reject_with_a_reason_re_queues_the_row_waiting_at_a_spec_checkpoint() -> None:
    world = parked("checkpoint", BUILD, "checkpoint")

    send(world, "answer", text="the plan misses the migration")

    assert world.status_of(BUILD) == "queued"


# ── continue ─────────────────────────────────────────────────────────────────


def test_continue_on_a_done_checkpoint_row_finishes_it_and_queues_the_next() -> None:
    world = parked("checkpoint", AFTER, "checkpoint")

    send(world, "continue")

    assert world.status_of(AFTER) == "done"
    assert world.status_of("push") == "queued"
    assert world.stored_run().status == "running"


def test_continue_on_an_agent_row_at_a_checkpoint_re_dispatches_that_row() -> None:
    world = parked("checkpoint", BUILD, "checkpoint")

    send(world, "continue")

    assert world.status_of(BUILD) == "queued"
    assert world.status_of("stories[0].verify") == "planned"


def test_continue_on_a_protected_path_park_resumes_the_row_and_keeps_the_files() -> None:
    world = parked("protected_path", BUILD, "error")

    outcome = send(world, "continue", files=["tests/unit/test_a.py"])

    assert world.status_of(BUILD) == "running"
    assert outcome.run.accepted_paths == ("tests/unit/test_a.py",)


def test_an_accepted_file_is_added_to_the_ones_an_earlier_continue_accepted() -> None:
    world = parked("protected_path", BUILD, "error", accepted_paths=("one.py",))

    outcome = send(world, "continue", files=["two.py"])

    assert outcome.run.accepted_paths == ("one.py", "two.py")


def test_continue_on_a_plan_stale_park_resumes_the_recorded_plan() -> None:
    """AD-13: `error → running → routed status`; the row's own completion moves the plan on."""
    world = parked("plan_stale", "plan", "error")

    send(world, "continue")

    assert world.status_of("plan") == "running"
    assert world.stored_run().status == "running"


def test_continue_on_a_checkpoint_that_is_the_last_row_ends_the_run() -> None:
    world = parked("checkpoint", "after", "checkpoint", plan=(("after", "checkpoint"),))

    outcome = send(world, "continue")

    assert outcome.run.status == "done"
    assert world.events() == ["continue", "done"]
    assert not outcome.resumed
    # the walk workflow is parked in `recv` and nothing remains to walk: it is stopped, or
    # it would sleep out HUMAN_WAIT_SECONDS holding its queue slot (AD-12; story 4-5's
    # `done-checkpoint` made a final checkpoint row the shipped case, fix 2026-09-18)
    assert engine_calls(world) == ["cancel"]


# ── retry ────────────────────────────────────────────────────────────────────


def test_retry_re_queues_the_errored_row_as_a_new_attempt() -> None:
    world = parked("timeout", "stories[0].verify", "error")

    outcome = send(world, "retry")

    assert world.status_of("stories[0].verify") == "queued"
    assert outcome.resumed
    assert world.records()[0].text == "retried by the operator"


# ── skip_story ───────────────────────────────────────────────────────────────


def test_skip_story_skips_the_frames_agent_rows_and_runs_its_verify_as_re_baseline() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "skip_story")

    assert world.status_of(BUILD) == "skipped"
    assert world.row(BUILD).reason == SKIPPED_BY_OPERATOR
    assert world.status_of("stories[0].verify") == "queued"
    assert world.status_of("stories[0].sync") == "planned"


def test_skip_story_re_resolves_the_frames_commit_message_to_the_operators_words() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "skip_story")

    resolved = world.row("stories[0].commit-guard").with_resolved

    assert resolved["message"] == "story 1: skipped by operator"
    assert SKIP_MESSAGE.format(story_id="1") == resolved["message"]


def test_skip_story_leaves_the_next_story_alone() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "skip_story")

    assert world.status_of("stories[1].build") == "planned"


def test_skip_story_queues_the_commit_row_when_the_repository_has_no_quality_gate() -> None:
    world = parked("blocked", BUILD, "blocked", statuses={"stories[0].verify": "skipped"})

    send(world, "skip_story")

    assert world.status_of("stories[0].commit-guard") == "queued"


def test_skip_story_also_skips_the_frames_own_checkpoint_row() -> None:
    world = parked("blocked", "stories[1].build", "blocked")

    send(world, "skip_story")

    assert world.status_of(AFTER) == "skipped"


def test_skip_story_on_a_verify_failed_park_re_queues_that_very_verify_row() -> None:
    """AD-13: "the frame's `verify` row runs as the re-baseline" — even when it is the stop."""
    world = parked("verify_failed", "stories[0].verify", "error")

    send(world, "skip_story")

    assert world.status_of("stories[0].verify") == "queued"
    assert world.status_of("stories[0].commit-guard") == "planned"


def test_skip_story_leaves_a_commit_row_that_already_ran_alone() -> None:
    world = parked("blocked", BUILD, "blocked", statuses={"stories[0].commit-guard": "done"})

    send(world, "skip_story")

    assert world.row("stories[0].commit-guard").with_resolved == {}


def test_skip_story_with_nothing_left_to_run_ends_the_run() -> None:
    world = parked("blocked", "stories[0].build", "blocked", plan=(("stories[0].build", "agent"),))

    outcome = send(world, "skip_story")

    assert outcome.run.status == "done"
    # revised 2026-09-18 with the `finished` fix (story 4-5's done-checkpoint surfaced it):
    # a signal that ends the Run stops its parked workflow instead of leaving it in `recv`
    # holding a queue slot for HUMAN_WAIT_SECONDS (AD-12); `[]` pinned the leak.
    assert engine_calls(world) == ["cancel"]


# ── skip_epic ────────────────────────────────────────────────────────────────


def test_skip_epic_on_an_epic_run_skips_every_remaining_story_frame() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "skip_epic")

    assert world.status_of(BUILD) == "skipped"
    assert world.status_of("stories[1].sync") == "skipped"
    assert world.status_of("stories[1].build") == "skipped"
    assert world.status_of(AFTER) == "skipped"


def test_skip_epic_leaves_the_epics_push_and_link_planned_so_the_commits_still_land() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "skip_epic")

    assert (world.status_of("push"), world.status_of("link")) == ("planned", "planned")
    assert world.status_of("stories[0].verify") == "queued"


def test_skip_epic_on_an_initiative_stops_at_the_epic_the_park_is_in() -> None:
    world = parked(
        "blocked",
        "epics[0].stories[0].build",
        "blocked",
        plan=INITIATIVE_PLAN,
        template_name="initiative",
    )

    send(world, "skip_epic")

    assert world.status_of("epics[0].stories[1].build") == "skipped"
    assert world.status_of("epics[1].stories[0].build") == "planned"
    assert world.status_of("epics[0].stories[0].verify") == "queued"


def test_skip_epic_parked_outside_a_story_frame_still_skips_the_epics_stories() -> None:
    world = parked(
        "timeout",
        "epics[0].baseline",
        "error",
        plan=INITIATIVE_PLAN,
        template_name="initiative",
    )

    send(world, "skip_epic")

    assert world.status_of("epics[0].stories[0].build") == "skipped"
    assert world.status_of("epics[0].stories[1].build") == "skipped"
    assert world.status_of("epics[0].push") == "queued"


def test_skip_epic_on_a_rejected_push_skips_the_push_and_link_then_starts_the_next_epic() -> None:
    world = parked(
        "push_rejected",
        "epics[0].push",
        "error",
        plan=INITIATIVE_PLAN,
        template_name="initiative",
    )

    send(world, "skip_epic")

    assert world.status_of("epics[0].push") == "skipped"
    assert world.status_of("epics[0].link") == "skipped"
    assert world.status_of("epics[1].checkout") == "queued"


#: An epic that ends with a done checkpoint, which a rejected push does not take with it.
PUSH_THEN_CHECKPOINT: tuple[tuple[str, str], ...] = (
    ("epics[0].push", "git.push"),
    ("epics[0].link", "pr.link"),
    ("epics[0].after", "checkpoint"),
    ("epics[1].checkout", "git.worktree"),
)


def test_a_rejected_push_takes_only_the_link_with_it_not_the_epics_done_checkpoint() -> None:
    """The epic's own stop for the Operator is still a stop: the Run resumes at it."""
    world = parked(
        "push_rejected",
        "epics[0].push",
        "error",
        plan=PUSH_THEN_CHECKPOINT,
        template_name="initiative",
    )

    send(world, "skip_epic")

    assert world.status_of("epics[0].link") == "skipped"
    assert world.status_of("epics[0].after") == "queued"
    assert world.status_of("epics[1].checkout") == "planned"


def test_skip_epic_on_a_rejected_push_of_the_last_epic_ends_the_run() -> None:
    world = parked("push_rejected", "push", "error", template_name="epic")

    outcome = send(world, "skip_epic")

    assert (world.status_of("push"), world.status_of("link")) == ("skipped", "skipped")
    assert outcome.run.status == "done"


def test_skip_epic_takes_the_error_verify_row_the_re_baseline_left_behind() -> None:
    """AD-13 lists that row for `skip_epic` where `skip_story` has to keep it runnable."""
    world = parked("verify_failed", "stories[0].verify", "error")

    send(world, "skip_epic")

    assert world.status_of("stories[0].verify") == "skipped"
    assert world.status_of("stories[0].commit-guard") == "queued"


def test_skip_epic_leaves_a_frame_row_that_is_already_finished_alone() -> None:
    world = parked("blocked", BUILD, "blocked", statuses={"stories[1].sync": "done"})

    send(world, "skip_epic")

    assert world.status_of("stories[1].sync") == "done"


# ── budget_raise ─────────────────────────────────────────────────────────────


def test_a_budget_raise_on_a_row_that_kept_its_routed_status_resumes_the_run() -> None:
    world = parked("budget", BUILD, "error", spend_usd=Decimal("9"))

    outcome = send(world, "budget_raise", budget_usd="20")

    assert outcome.run.budget_usd == Decimal("20")
    assert outcome.run.status == "running"
    assert engine_calls(world) == ["signal"]


def test_a_budget_raise_over_a_blocked_row_re_parks_the_run_at_that_row() -> None:
    """AD-13: the Run stays `needs_you`, the Question is still the earlier gate record."""
    world = parked("budget", BUILD, "blocked", spend_usd=Decimal("9"))

    outcome = send(world, "budget_raise", budget_usd="20")

    assert (outcome.run.status, outcome.run.park_kind) == ("needs_you", "blocked")
    assert outcome.run.park_reason == "why it stopped"
    assert outcome.run.budget_usd == Decimal("20")
    assert engine_calls(world) == []
    assert not outcome.resumed


def test_a_budget_raise_over_a_checkpoint_row_re_parks_it_the_same_way() -> None:
    world = parked("budget", AFTER, "checkpoint", spend_usd=Decimal("9"))

    assert send(world, "budget_raise", budget_usd="20").run.park_kind == "checkpoint"


def test_a_budget_raise_on_a_run_level_park_resumes_it() -> None:
    """`Park.path` is optional; a Run parked without a row has no routed status to keep."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        park_kind="budget",
        park_reason="budget 9.00 / 10.00",
        spend_usd=Decimal("9"),
    )

    assert send(world, "budget_raise", budget_usd="20").run.status == "running"


# ── cancel ───────────────────────────────────────────────────────────────────


def test_cancel_skips_every_row_that_has_not_started_and_ends_the_run() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "done", "checkout": "running"})

    outcome = send(world, "cancel")

    assert outcome.run.status == "cancelled"
    assert outcome.run.ended_at == world.clock.now()
    assert world.status_of("baseline") == "skipped"
    assert world.status_of("checkout") == "running"
    assert world.status_of("plan") == "done"


def test_cancel_stops_the_workflow_rather_than_waking_it() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "running"})

    outcome = send(world, "cancel")

    assert engine_calls(world) == ["cancel"]
    assert not outcome.resumed
    assert world.records()[0].event == "cancel"


def test_cancel_hands_back_the_live_process_groups_and_the_worktrees() -> None:
    worktree = Worktree(branch="feat/x", path="/work/wt/x", created_branch=True, pushed=False)
    world = a_world("running", EPIC_PLAN, {"plan": "running"}, worktrees=(worktree,))
    an_attempt(world, "plan", pgid=4242)

    outcome = send(world, "cancel")

    assert outcome.cancel_plan == CancelPlan(pgids=(4242,), worktrees=(worktree,))


def test_a_finished_attempts_process_group_is_not_offered_for_killing() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "done", "checkout": "running"})
    an_attempt(world, "plan", pgid=4242, ended_at=world.clock.now())

    outcome = send(world, "cancel")

    assert outcome.cancel_plan == CancelPlan(pgids=(), worktrees=())


def test_a_started_row_with_no_attempt_at_all_contributes_no_process_group() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "running"})

    assert send(world, "cancel").cancel_plan == CancelPlan(pgids=(), worktrees=())


def test_a_run_that_has_not_started_yet_can_be_cancelled() -> None:
    """AD-8 has `queued → cancelled`; the Board offers Cancel on a Run behind the lock."""
    world = a_world("queued", EPIC_PLAN)

    outcome = send(world, "cancel")

    assert outcome.run.status == "cancelled"
    assert outcome.run.ended_at == world.clock.now()
    assert world.status_of("plan") == "skipped"
    assert engine_calls(world) == ["cancel"]


def test_a_parked_run_can_be_cancelled_too() -> None:
    world = parked("blocked", BUILD, "blocked")

    outcome = send(world, "cancel")

    assert outcome.run.status == "cancelled"
    assert outcome.run.park_kind is None


# ── the terminal kinds ───────────────────────────────────────────────────────


def test_terminal_start_marks_the_session_and_leaves_the_run_parked() -> None:
    world = parked("blocked", BUILD, "blocked")

    outcome = send(world, "terminal_start")

    assert outcome.run.terminal_session
    assert outcome.run.status == "needs_you"
    assert engine_calls(world) == []
    assert world.records()[0].text == "terminal session started"


def test_terminal_release_hands_the_run_back() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    assert not send(world, "terminal_release").run.terminal_session


def test_a_terminal_release_on_a_running_run_does_not_wake_the_engine() -> None:
    """It is admitted in every non-terminal status and applies no Run transition at all."""
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, terminal_session=True)

    outcome = send(world, "terminal_release")

    assert outcome.run.status == "running"
    assert not outcome.resumed
    assert engine_calls(world) == []


def test_terminal_resume_finishes_the_story_row_and_starts_the_next_one() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    outcome = send(world, "terminal_resume")

    assert world.status_of(BUILD) == "done"
    assert world.status_of("stories[0].verify") == "queued"
    assert (outcome.run.status, outcome.run.terminal_session) == ("running", False)
    assert engine_calls(world) == ["signal"]


def test_the_terminal_resume_record_names_the_terminal_as_the_actor() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    send(world, "terminal_resume")

    assert world.records()[0].actor == "terminal"


def test_terminal_resume_on_the_last_row_of_a_plan_ends_the_run() -> None:
    world = parked("blocked", "build", "blocked", plan=(("build", "agent"),), terminal_session=True)

    assert send(world, "terminal_resume").run.status == "done"


# ── the refusals ─────────────────────────────────────────────────────────────


def test_an_invalid_signal_writes_nothing_at_all() -> None:
    world = parked("blocked", BUILD, "blocked")

    with pytest.raises(Conflict) as raised:
        send(world, "retry")

    assert str(raised.value) == "signal retry invalid for status needs_you / park blocked"
    assert world.records() == []
    assert world.status_of(BUILD) == "blocked"
    assert not world.ports.uow.committed
    assert engine_calls(world) == []


def test_a_signal_to_a_run_that_is_not_stored_is_a_not_found() -> None:
    world = parked("blocked", BUILD, "blocked")

    with pytest.raises(NotFound):
        signal_run(world.signal_ports, new_id(), Signal(kind="cancel"))


def test_a_signal_is_one_committed_unit_of_work_and_the_engine_is_told_after_it() -> None:
    """AD-8: a woken workflow never reads a Run whose writes are not durable yet."""
    world = parked("blocked", BUILD, "blocked")

    send(world, "answer", text="go on")

    assert world.ports.uow.calls == ["enter", "commit", "exit"]
    assert world.engine.committed_when_called == [True]


def test_a_cancel_reaches_the_engine_after_the_commit_too() -> None:
    world = a_world("running", EPIC_PLAN, {"plan": "running"})

    send(world, "cancel")

    assert world.engine.committed_when_called == [True]


def test_the_engine_is_handed_the_operators_own_signal_for_this_run() -> None:
    """The resumed step reads the payload: a wake with the wrong one loses the Answer."""
    world = parked("blocked", BUILD, "blocked")
    signal = Signal(kind="answer", payload={"text": "use the psycopg adapter"})

    signal_run(world.signal_ports, world.run.id, signal)

    assert world.engine.calls == [("signal", (world.run.id, signal))]
