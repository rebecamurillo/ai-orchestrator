"""`signal_run` behaviour for dependency-parked Runs (story 5-4).

Coverage:
- `cancel` on a dependency-parked (`needs_you` / `park_kind="dependency"`) Run:
    - parks all saved dependents of *that* run
    - does NOT call `engine.cancel` (the run was never enqueued)
    - returns `cancelled` status

- `continue` on a dependency-parked Run ("start anyway"):
    - clears `park_kind`, clears `after_run_id`
    - calls `engine.enqueue` (not `engine.signal`)
    - writes `engine_ref` on the run
    - does NOT call `engine.cancel`

- `cancel` on a *queued* run with `engine_ref={}` (not a dependency park):
    - DOES call `engine.cancel` (the existing test behaviour is preserved)
"""

from __future__ import annotations

from orchestrator.application.use_cases.signal_run import SignalOutcome, signal_run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world, build_run


def _send(world, kind: str, **payload) -> SignalOutcome:
    return signal_run(world.signal_ports, world.run.id, Signal(kind=kind, payload=payload))


def _engine_calls(world) -> list[str]:
    return [name for name, _ in world.engine.calls]


# ── cancel on dependency-parked run ──────────────────────────────────────────


def test_cancel_dependency_park_returns_cancelled() -> None:
    """Cancelling a dependency-parked Run transitions it to cancelled."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    outcome = _send(world, "cancel")

    assert outcome.run.status == "cancelled"


def test_cancel_dependency_park_does_not_call_engine_cancel() -> None:
    """A dependency-parked Run was never enqueued — engine.cancel must NOT be called."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    _send(world, "cancel")

    assert "cancel" not in _engine_calls(world)


def test_cancel_dependency_park_parks_saved_dependent_of_this_run() -> None:
    """Cancelling a dependency-parked Run also parks the Runs that were waiting for it."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )
    # This run's own dependent (waiting for this run to finish).
    this_run = world.stored_run()
    their_dependent = build_run(status="queued", after_run_id=this_run.id, engine_ref={})
    # Inject the dependent into the existing runs repository directly.
    world.ports.runs.add(their_dependent)

    _send(world, "cancel")

    stored_dep = world.ports.runs.get(their_dependent.id)
    assert stored_dep is not None
    assert stored_dep.status == "needs_you"
    assert stored_dep.park_kind == "dependency"


# ── continue on dependency-parked run ("start anyway") ───────────────────────


def test_continue_dependency_park_calls_engine_enqueue() -> None:
    """`continue` on a dependency park enqueues the Run immediately."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    _send(world, "continue")

    assert "enqueue" in _engine_calls(world)


def test_continue_dependency_park_does_not_call_engine_signal() -> None:
    """`continue` on a dependency park enqueues — it must not also call engine.signal."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    _send(world, "continue")

    assert "signal" not in _engine_calls(world)


def test_continue_dependency_park_clears_park_kind() -> None:
    """`continue` clears `park_kind` so the run is no longer seen as dependency-parked."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    outcome = _send(world, "continue")

    assert outcome.run.park_kind is None


def test_continue_dependency_park_clears_after_run_id() -> None:
    """`continue` clears `after_run_id` so the startup sweep won't re-enqueue it."""
    predecessor_id = new_id()
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
        after_run_id=predecessor_id,
    )

    outcome = _send(world, "continue")

    assert outcome.run.after_run_id is None


def test_continue_dependency_park_sets_engine_ref() -> None:
    """`continue` writes the engine_ref returned by enqueue onto the Run."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    outcome = _send(world, "continue")

    # engine_ref must be non-empty (the fake engine returns {"ref": N}).
    assert outcome.run.engine_ref


def test_continue_dependency_park_returns_resumed_false() -> None:
    """`continue` on a dependency park returns `resumed=False` (the engine is not woken)."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    outcome = _send(world, "continue")

    assert outcome.resumed is False


# ── cancel on a queued run (engine_ref={}) — regression ─────────────────────


def test_cancel_queued_run_without_park_kind_still_calls_engine_cancel() -> None:
    """A queued Run with engine_ref={} and no park_kind must still call engine.cancel.

    This pins the existing behaviour covered by the frozen test
    `test_a_run_that_has_not_started_yet_can_be_cancelled` — the guard in `_tell_the_engine`
    is on `original_park_kind != "dependency"`, not on `engine_ref`, so a queued run with
    the default empty engine_ref and no park_kind still reaches `engine.cancel`.
    """
    # A queued Run with no park_kind (the default saved run state).
    world = a_world("queued", PAIR_PLAN)

    _send(world, "cancel")

    assert "cancel" in _engine_calls(world)
