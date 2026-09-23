"""`signal_initiative` — AD-13's initiative-wide `cancel` (multi-repo initiative S8).

Each test builds a small set of member Runs directly (`writer_fixtures.build_run`), wires
them into one `FakeRunRepository` shared by one `SignalPorts`, and reads the result back off
the repository and the outcome — the same shape `test_signal_run.py` reads its own writes in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.signal_initiative import (
    SignalInitiativeOutcome,
    signal_initiative,
)
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import RunStatus
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

SLUG = "q4"
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def a_member(
    order: int,
    status: RunStatus = "queued",
    after_run_ids: tuple = (),
    **over: object,
) -> Run:
    """One member Run, created `order` seconds after `EPOCH` — `list_by_initiative`'s own
    `(created_at, id)` ordering reads this as creation order (`tests/unit/fakes/runs.py`)."""
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic-fixture",
        "template_version": 1,
        "status": status,
        "budget_usd": Decimal("10"),
        "initiative": SLUG,
        "after_run_ids": after_run_ids,
        "created_at": EPOCH + timedelta(seconds=order),
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


class World:
    """One `SignalPorts`, wired over a `FakeRunRepository` the test seeds directly."""

    def __init__(self, members: list[Run]) -> None:
        self.runs = FakeRunRepository(members)
        clock = FakeClock(EPOCH)
        uow = FakeUnitOfWork()
        self.writers = WriterPorts(
            runs=self.runs,
            steps=FakeStepRunRepository([]),
            attempts=FakeAttemptRepository(),
            records=FakeGateRecordRepository(),
            uow=uow,
            clock=clock,
        )
        self.engine = FakeWorkflowEngine(clock=clock, uow=uow)
        self.ports = SignalPorts(writers=self.writers, engine=self.engine)

    def status_of(self, run: Run) -> RunStatus:
        stored = self.runs.get(run.id)
        assert stored is not None
        return stored.status

    def cancel(self, slug: str = SLUG) -> SignalInitiativeOutcome:
        return signal_initiative(self.ports, slug, "cancel")


# ── the kind gate ──────────────────────────────────────────────────────────────


def test_a_kind_other_than_cancel_is_a_422_invalid() -> None:
    world = World([a_member(0, "running")])

    with pytest.raises(Invalid, match="retry"):
        signal_initiative(world.ports, SLUG, "retry")


def test_an_unknown_slug_is_a_404_not_found() -> None:
    world = World([a_member(0, "running")])

    with pytest.raises(NotFound, match="never-dispatched"):
        world.cancel("never-dispatched")


# ── which members are signalled ───────────────────────────────────────────────


def test_every_non_terminal_status_is_signalled() -> None:
    running = a_member(0, "running")
    queued = a_member(1, "queued")
    needs_you = a_member(2, "needs_you", park_kind="checkpoint", park_path=None)
    world = World([running, queued, needs_you])

    outcome = world.cancel()

    assert set(outcome.signalled) == {running.id, queued.id, needs_you.id}
    assert outcome.skipped == ()
    for member in (running, queued, needs_you):
        assert world.status_of(member) == "cancelled"


def test_an_already_terminal_member_is_skipped_and_left_untouched() -> None:
    done = a_member(0, "done")
    running = a_member(1, "running")
    world = World([done, running])

    outcome = world.cancel()

    assert outcome.skipped == (done.id,)
    assert outcome.signalled == (running.id,)
    assert world.status_of(done) == "done"
    assert world.writers.records.list_for_run(done.id) == []


def test_every_member_already_terminal_signals_nothing() -> None:
    failed = a_member(0, "failed")
    cancelled = a_member(1, "cancelled")
    world = World([failed, cancelled])

    outcome = world.cancel()

    assert outcome.signalled == ()
    assert set(outcome.skipped) == {failed.id, cancelled.id}


# ── dependents-first ordering ─────────────────────────────────────────────────


def test_a_dependent_is_cancelled_before_the_predecessor_it_names() -> None:
    predecessor = a_member(0, "running")
    dependent = a_member(1, "queued", after_run_ids=(predecessor.id,))
    world = World([predecessor, dependent])

    outcome = world.cancel()

    assert outcome.signalled == (dependent.id, predecessor.id)


def test_a_chain_cancels_dependents_first_and_an_unrelated_member_by_reverse_creation() -> None:
    """`a` → `b` → `c` is a dependency chain (`b` waits on `a`, `c` waits on `b`);
    `d` names no edge to any of them. Reverse-topo puts `c` before `b` before `a`; `d`, tied
    with nothing, sorts by reverse creation order — created last, signalled first."""
    a = a_member(0, "running")
    b = a_member(1, "queued", after_run_ids=(a.id,))
    c = a_member(2, "queued", after_run_ids=(b.id,))
    d = a_member(3, "queued")
    world = World([a, b, c, d])

    outcome = world.cancel()

    assert outcome.signalled == (d.id, c.id, b.id, a.id)


def test_an_edge_to_a_run_outside_the_initiative_is_ignored() -> None:
    """`after_run_ids` can in principle name a Run that is not itself a member of this
    initiative's own read (`initiative_view.py`'s own defensive precedent); the sort only
    orders *these* members, so such an edge is simply not one of its constraints."""
    outsider_id = new_id()
    member = a_member(0, "running", after_run_ids=(outsider_id,))
    world = World([member])

    outcome = world.cancel()

    assert outcome.signalled == (member.id,)
