"""A row an Operator's signal left `running`, and the walk that has to pick it up (AD-13).

Most resumed rows go back on the queue: `answer` is `blocked → queued`, `retry` is
`error → queued`, `continue` on an `agent` row at a review checkpoint is
`checkpoint → queued`. One does not. AD-13 gives `continue` on a `plan_stale` — and on a
`protected_path` — park the transition `error → running → routed status`, and AD-8's Step
diagram has no `error → done`, so `continue_accept` writes the row `running` in place and
the row itself is expected to run once more: `application/steps/plan_check.py` has a branch
for exactly that, answering `done` on a `continue` resume signal without re-reading anything.

Nothing ran it. `next_row` asked `first_queued` and then `_start_the_plan`, which refuses a
Run holding a row outside `planned`/`done`/`skipped` — a `running` row among them — so the
walk fell through to `close_run`, which reads an unfinished row as a stall and parks
`internal`. The Operator's `continue` therefore moved a recoverable `plan_stale` park to an
`internal` one that admits no signal but `cancel`: the Run was unrecoverable, and every
`epic@1` Run parked on row 1 had that as its only continuation.

So `next_row` answers with the row a signal resumed in place. `start_attempt` already
tolerates a `running` row — that is FR-12's interrupted-attempt rule, which numbers the next
Attempt after the one that stopped — so the row runs, its executor sees the `continue`
record as `resume_signal`, and `apply_step_result` queues the successor from there.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepPorts

# `plan.check`'s executor registers itself on import (AD-9: one module, one registry entry),
# and this walk runs row 1 through the real one — the `continue` branch is half the rule
# being proven, so a recording double would assert the walk and not the behaviour.
from orchestrator.application.steps.plan_check import CONTINUE
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.walk import (
    WalkPorts,
    apply_result,
    attempt_row,
    close_run,
    next_row,
)
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

REFERENCE = {"workflow_id": "w-1", "step_id": 1}
WORK_DIR = "/work"

#: The row `plan.check` is, and the row after it — `PAIR_PLAN`'s two.
PLAN = "plan"
CHECKOUT = "checkout"
FIRST, SECOND = 1, 2

#: What `plan_check_row` puts on row 1. Empty maps: this Run recorded no list file, so the
#: check has nothing to re-read and could not park on drift even if it looked.
PLAN_RESOLVED = {
    "base_dir": "/work/acme/widget/base",
    "url": "https://github.test/acme/widget.git",
    "base_branch": "main",
    "plan_refs": {},
    "list_branches": {},
}


def parked_on_plan_stale() -> World:
    """A Run stopped exactly as `PlanCheckExecutor` stops one: row 1 `error`, park named."""
    return a_world(
        "needs_you",
        PAIR_PLAN,
        {PLAN: "error"},
        {PLAN: PLAN_RESOLVED},
        park_kind="plan_stale",
        park_path=PLAN,
        park_reason="plan stale: docs/epic-1/stories.yaml",
    )


def ports_of(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def resume(world: World) -> None:
    """The Operator's `continue`, through the one writer of an Operator transition (AD-8)."""
    signal_run(world.signal_ports, world.run.id, Signal(kind=CONTINUE, payload={}))


def walk_once(world: World) -> str | None:
    """One turn of the walker's loop, as `infrastructure/dbos/walker.py` runs it."""
    ports = ports_of(world)
    seq = next_row(ports, world.run.id)
    if seq is None:
        return close_run(ports, world.run.id)
    result = attempt_row(ports, world.run.id, seq, REFERENCE, CONTINUE)
    return apply_result(ports, world.run.id, seq, result)


# ── what the signal leaves behind ───────────────────────────────────────────


def test_the_signal_leaves_the_row_running_and_nothing_queued() -> None:
    """The premise, stated once: AD-13's `error → running` writes no queued row."""
    world = parked_on_plan_stale()

    resume(world)

    assert world.status_of(PLAN) == "running"
    assert world.ports.steps.first_queued(world.run.id) is None


# ── and what the walk then does with it ─────────────────────────────────────


def test_the_walk_takes_the_row_the_signal_resumed_in_place() -> None:
    world = parked_on_plan_stale()
    resume(world)

    assert next_row(ports_of(world), world.run.id) == FIRST


def test_a_resumed_row_ahead_of_no_queue_does_not_start_the_plan_over() -> None:
    """The later rows stay `planned`: the resumed row is the one to run, not row 2."""
    world = parked_on_plan_stale()
    resume(world)

    next_row(ports_of(world), world.run.id)

    assert world.status_of(CHECKOUT) == "planned"


def test_the_resumed_row_runs_and_its_successor_is_queued() -> None:
    """`plan.check`'s own `continue` branch answers `done` without re-reading (AD-13)."""
    world = parked_on_plan_stale()
    resume(world)

    status = walk_once(world)

    assert status == "running"
    assert world.status_of(PLAN) == "done"
    assert world.status_of(CHECKOUT) == "queued"


def test_the_resumed_row_records_the_next_attempt_rather_than_reusing_the_parked_one() -> None:
    """FR-12's numbering: the attempt that parked stays attempt 1, and this one is 2."""
    world = parked_on_plan_stale()
    an_attempt(world, PLAN, FIRST, status="error", ended_at=EPOCH)
    resume(world)

    walk_once(world)

    assert [attempt.n for attempt in world.attempts_of(PLAN)] == [FIRST, SECOND]


def test_the_walk_reaches_done_rather_than_the_internal_park_the_defect_left() -> None:
    """The defect's own signature was `no runnable step: plan is running`, `park_kind`
    `internal` — a park whose only admitted signal is `cancel`. Here the resumed row is the
    Run's last unfinished one, so the same turn that runs it also ends the Run: the reading
    is taken off the stored Run rather than off one call's return value."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        {PLAN: "error", CHECKOUT: "skipped"},
        {PLAN: PLAN_RESOLVED},
        park_kind="plan_stale",
        park_path=PLAN,
        park_reason="plan stale: docs/epic-1/stories.yaml",
    )
    resume(world)

    assert walk_once(world) == "done"
    assert world.stored_run().park_kind is None
    assert "internal" not in world.events()


def test_a_queued_row_is_still_preferred_to_a_row_left_running() -> None:
    """The queue is the walk's own order; the in-place resume is the fallback, not a jump."""
    world = a_world("running", PAIR_PLAN, {PLAN: "running", CHECKOUT: "queued"})

    assert next_row(ports_of(world), world.run.id) == SECOND
