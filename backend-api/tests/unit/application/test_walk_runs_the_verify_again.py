"""FR-10's second half: the `verify` row a redispatch sent the walk back from runs again.

`on_fail: {redispatch: build, max: 1}` is a *loop*, and until story 6-8 only its first turn
existed. `apply_step_result::_redispatch` wrote the target `queued`, and deliberately left
every row between the target and the sender as it stood (AD-9, and
`test_apply_step_result.py` pins exactly that). The sender is the `verify` row the caller
has just written `error`, so when the re-dispatched `build` finished, `_advance` looked at
its successor, found a row that was neither `planned` nor `skipped`, and correctly declined
to touch it — leaving a Run with nothing queued, nothing running, and one `error` row.
`close_run` reads that as a stall and parks `internal`, a stop that admits no signal but
`cancel`.

So every Run whose quality gate failed once was unrecoverable, and `verify failed {n}/{n}`
— AD-9's own "exhaustion parks the Run" — could never be reached at all. Found by
`tests/e2e/test_uj3.py`'s scenario C, which is the first thing to drive a real gate failure
through the whole walk; fixed in `walk.py::_sent_back`, `_resumed_in_place`'s twin.

Nothing here is a double for the rule: the assertions are `next_row`'s own answer and the
row statuses it left, over the same fakes every other walk test uses.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepPorts
from orchestrator.application.use_cases.walk import WalkPorts, next_row
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"

#: `EPIC_PLAN`'s own seq numbers: `build` is the fifth row, `verify` the sixth.
BUILD_SEQ = 5
VERIFY_SEQ = 6

#: What the planner resolves `on_fail: {redispatch: build, max: 1}` into on the `verify`
#: row: `plan_model.REDISPATCH_TARGET_SEQ` holding the target's own `seq`, never its id
#: or its step id (`templates/plan.py::_resolved_on_fail`).
REDISPATCH_TO_BUILD = {"on_fail": {"target_seq": BUILD_SEQ, "max": 1}}


def ports_of(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def a_redispatched_world(build_status: str, status_over: str = "running", **over: object) -> World:
    """A Run mid-redispatch: `verify` errored and sent the walk back to `build`."""
    return a_world(
        status_over,
        EPIC_PLAN,
        {BUILD: build_status, VERIFY: "error"},
        {VERIFY: REDISPATCH_TO_BUILD},
        **over,
    )


# ── the loop closes ─────────────────────────────────────────────────────────────────────


def test_the_verify_row_is_queued_again_once_its_redispatch_target_has_finished() -> None:
    """The whole fix: `build` re-ran and is `done`, so the gate that sent it back runs."""
    world = a_redispatched_world("done")

    seq = next_row(ports_of(world), world.run.id)

    assert seq == VERIFY_SEQ
    assert world.status_of(VERIFY) == "queued"
    assert world.ports.uow.committed


def test_the_run_is_not_stalled_any_more_so_nothing_parks_it_internal() -> None:
    """The symptom, stated as the assertion it failed: `next_row` answering `None` here is
    what `close_run` turned into `no runnable step: stories[0].verify is error`."""
    world = a_redispatched_world("done")

    assert next_row(ports_of(world), world.run.id) is not None


def test_a_skipped_target_also_lets_the_gate_run_again() -> None:
    """`skipped` is finished too (`writers.FINISHED`): `skip_story` marks the frame's agent
    row `skipped` and the same `verify` row is exactly what the re-baseline re-runs."""
    world = a_redispatched_world("skipped")

    assert next_row(ports_of(world), world.run.id) == VERIFY_SEQ


# ── and nothing else is touched ─────────────────────────────────────────────────────────


def test_a_run_the_exhausted_bound_parked_is_never_resumed_by_this_rule() -> None:
    """The rows an exhausted redispatch leaves are byte for byte the ones mid-loop leaves
    — target `done`, gate `error` — and the only difference is that `_redispatch` parked
    the Run on it. Resuming here would run straight past the Operator's own stop, and no
    row-status guard can tell the two apart; the Run's own status is what does."""
    world = a_redispatched_world("done", status_over="needs_you")

    assert next_row(ports_of(world), world.run.id) is None
    assert world.status_of(VERIFY) == "error"


def test_a_queued_run_that_has_not_started_is_left_to_the_planner() -> None:
    """`next_row` queues the plan's first row on a `queued` Run; this rule answers
    nothing there, so `_start_the_plan` still decides that case alone."""
    world = a_world("queued", EPIC_PLAN, None, {VERIFY: REDISPATCH_TO_BUILD})

    assert next_row(ports_of(world), world.run.id) == 1


def test_a_target_still_running_is_answered_before_the_gate_that_sent_the_walk_back() -> None:
    """Order matters and is unchanged: `_resumed_in_place` is asked first, so the row the
    walk is already on wins and the gate keeps waiting for it."""
    world = a_redispatched_world("running")

    assert next_row(ports_of(world), world.run.id) == BUILD_SEQ
    assert world.status_of(VERIFY) == "error"


def test_a_queued_row_still_wins_over_the_gate_that_sent_the_walk_back() -> None:
    """`first_queued` is asked first and stays the whole order: the re-dispatched `build` is
    what runs, and the gate waits for it."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {BUILD: "queued", VERIFY: "error"},
        {VERIFY: REDISPATCH_TO_BUILD},
    )

    assert next_row(ports_of(world), world.run.id) == BUILD_SEQ
    assert world.status_of(VERIFY) == "error"


def test_an_errored_row_that_redispatches_nowhere_is_left_where_it_is() -> None:
    """`on_fail: fail` and `on_fail: escalate` are strings, not redispatches — an `error`
    row carrying one is a stop, and resurrecting it would run past the Operator."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {BUILD: "done", VERIFY: "error"},
        {VERIFY: {"on_fail": "fail"}},
    )

    assert next_row(ports_of(world), world.run.id) is None
    assert world.status_of(VERIFY) == "error"


def test_a_gate_pointing_at_a_row_that_has_not_finished_is_left_where_it_is() -> None:
    """The target is read by `seq`: a redispatch aimed at a row no `done`/`skipped` row
    matches is not this rule's business, whatever else the Run holds."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {BUILD: "error", VERIFY: "error"},
        {VERIFY: REDISPATCH_TO_BUILD},
    )

    assert next_row(ports_of(world), world.run.id) is None
    assert world.status_of(VERIFY) == "error"
