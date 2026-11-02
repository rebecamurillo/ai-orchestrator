"""Story 2-1, review fix: a `pause` and the step that is finishing write the same Run row.

SQLAlchemy writes only the columns an entity changed from the snapshot it was read as. A
writer holding a stale snapshot therefore leaves another writer's columns alone, and a
`pause_requested` committed in between survives a park that never saw it, or lands on a Run
that is no longer running. Both writers read the Run under a row lock (`get_for_update`), so
the second one sees what the first committed. `RacingRuns` models exactly that: an unlocked
read is a snapshot taken before the other writer lands, a locked read waits for it."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Park, Signal, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.runs import FakeRunRepository

BUILD = "stories[0].build"
LOCKED = 2
VERIFY = "stories[0].verify"
DONE = StepResult(status="done", gate="deterministic")
BLOCKED = StepResult(
    status="blocked",
    gate="liveness",
    reason="intent gap",
    park=Park(kind="blocked", reason="intent gap", path=BUILD),
)


class RacingRuns(FakeRunRepository):
    """One other writer commits between this transaction's first read and its writes."""

    def __init__(self, run: Run, other: Callable[[Run], Run]) -> None:
        super().__init__([run])
        self._other: Callable[[Run], Run] | None = other
        self._snapshot: Run | None = None

    def _land(self, run_id: UUID) -> None:
        if self._other is not None:
            self.runs[run_id] = self._other(self.runs[run_id])
            self._other = None

    def get(self, run_id: UUID) -> Run | None:
        self._snapshot = self.runs.get(run_id)
        self._land(run_id)
        return self._snapshot

    def get_for_update(self, run_id: UUID) -> Run | None:
        self.calls.append(("get_for_update", run_id))
        self._land(run_id)
        self._snapshot = self.runs.get(run_id)
        return self._snapshot

    def update(self, run: Run) -> None:
        assert self._snapshot is not None
        changed = {
            field: getattr(run, field)
            for field in Run.model_fields
            if getattr(run, field) != getattr(self._snapshot, field)
        }
        self.runs[run.id] = self.runs[run.id].model_copy(update=changed)


def racing_world(status: str, other: Callable[[Run], Run], **over: object) -> World:
    world = a_world(status, EPIC_PLAN, {BUILD: "running"}, **over)  # type: ignore[arg-type]
    an_attempt(world, BUILD)
    runs = RacingRuns(world.run, other)
    world.ports = world.ports.__class__(**{**world.ports.__dict__, "runs": runs})
    return world


def pause_lands(run: Run) -> Run:
    return run.model_copy(update={"pause_requested": True})


def park_lands(run: Run) -> Run:
    return run.model_copy(
        update={
            "status": "needs_you",
            "park_kind": "blocked",
            "park_path": BUILD,
            "park_reason": "intent gap",
            "park_seq": 1,
        }
    )


@pytest.mark.parametrize("result", [DONE, BLOCKED], ids=["finishes", "parks by itself"])
def test_a_pause_that_lands_as_a_row_ends_never_leaves_a_stale_flag(result: StepResult) -> None:
    world = racing_world("running", pause_lands)

    apply_step_result(world.ports, world.run.id, world.row(BUILD).seq, result)

    run = world.stored_run()
    assert run.pause_requested is False
    assert run.status == "needs_you"
    assert run.park_kind == ("paused" if result is DONE else "blocked")


def test_a_pause_that_lands_on_the_last_row_leaves_no_flag_on_the_finished_run() -> None:
    world = a_world("running", (("only", "shell"),), {"only": "running"})
    an_attempt(world, "only")
    world.ports = world.ports.__class__(
        **{**world.ports.__dict__, "runs": RacingRuns(world.run, pause_lands)}
    )

    apply_step_result(world.ports, world.run.id, 1, DONE)

    run = world.stored_run()
    assert (run.status, run.pause_requested) == ("done", False)


def test_a_pause_validated_against_a_run_that_has_since_parked_is_refused() -> None:
    world = racing_world("running", park_lands)

    with pytest.raises(Conflict, match="invalid for status needs_you"):
        signal_run(world.signal_ports, world.run.id, Signal(kind="pause"))

    run = world.stored_run()
    assert run.pause_requested is False
    assert world.events() == []


def test_both_writers_read_the_run_under_the_lock() -> None:
    world = racing_world("running", pause_lands)

    apply_step_result(world.ports, world.run.id, world.row(BUILD).seq, DONE)
    signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind="continue", stop=world.stored_run().park_seq),
    )

    calls = world.ports.runs.calls  # type: ignore[attr-defined]
    assert [name for name, _ in calls if name == "get_for_update"] == ["get_for_update"] * LOCKED
