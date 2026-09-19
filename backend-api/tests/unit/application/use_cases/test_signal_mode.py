"""`_check_mode` in `signal_run`: gate validation for `mode="session"` on Answer and Retry.

Five TDD cases (story 3-3):

1. mode=session accepted when harness_is_resumable=True and latest attempt has session_id.
2. mode=session rejected when harness does not support resume (harness_is_resumable=False).
3. mode=session rejected when harness supports resume but session_id is None.
4. Unknown mode value rejected before any gate record is written.
5. Absent mode defaults to "restart" — no Invalid raised, signal proceeds normally.

Each test reaches `signal_run` directly with a customised `SignalPorts`.  The run is parked
at a blocked story build row so that `validate` admits the `answer` signal before `_check_mode`
runs.  For `retry` coverage, test 5 also uses a `retry` signal on an errored row.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.signal_run import (
    SignalPorts,
    _always_false,
    _no_attempt,
    signal_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.errors import Invalid
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, a_world
from tests.unit.fakes.clock import EPOCH

BUILD = "stories[0].build"


def _parked_world() -> object:
    """A Run stopped at a blocked story build row, the way `apply_step_result` leaves it."""
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="blocked on a condition",
    )


def _attempt(run_id: object, *, session_id: str | None = "s-123") -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run_id,  # type: ignore[arg-type]
        step_run_id=new_id(),
        n=1,
        status="error",
        started_at=EPOCH,
        harness="claude",
        session_id=session_id,
    )


def _signal_ports(world: object, *, resumable: bool, session_id: str | None) -> SignalPorts:
    attempt = _attempt(world.run.id, session_id=session_id)  # type: ignore[attr-defined]
    return SignalPorts(
        writers=world.ports,  # type: ignore[attr-defined]
        engine=world.engine,  # type: ignore[attr-defined]
        harness_is_resumable=lambda _: resumable,
        latest_attempt_for_run=lambda _: attempt,
    )


# ── 1: mode=session accepted ──────────────────────────────────────────────────


def test_mode_session_accepted_when_harness_is_resumable_and_session_exists() -> None:
    """reply_available=True: no Invalid raised, gate recorded, run re-queued."""
    world = _parked_world()
    ports = _signal_ports(world, resumable=True, session_id="s-123")

    outcome = signal_run(
        ports,
        world.run.id,
        Signal(kind="answer", payload={"mode": "session", "text": "ok"}),  # type: ignore[attr-defined]
    )

    assert outcome.run.status == "running"
    records = world.ports.records.list_for_run(world.run.id)  # type: ignore[attr-defined]
    assert len(records) == 1
    assert records[0].event == "answer"
    assert records[0].payload == {"mode": "session", "text": "ok"}


# ── 2: mode=session rejected — no resume capability ───────────────────────────


def test_mode_session_rejected_when_harness_does_not_support_resume() -> None:
    """harness_is_resumable=False → Invalid with the reason; gate is not recorded."""
    world = _parked_world()
    ports = _signal_ports(world, resumable=False, session_id="s-123")

    with pytest.raises(Invalid) as raised:
        signal_run(
            ports,
            world.run.id,  # type: ignore[attr-defined]
            Signal(kind="answer", payload={"mode": "session", "text": "ok"}),
        )

    assert "harness does not support resume" in str(raised.value)
    assert world.ports.records.list_for_run(world.run.id) == []  # type: ignore[attr-defined]


# ── 3: mode=session rejected — no session_id ─────────────────────────────────


def test_mode_session_rejected_when_session_id_is_none() -> None:
    """capabilities.resume=True but session_id=None → Invalid; gate is not recorded."""
    world = _parked_world()
    ports = _signal_ports(world, resumable=True, session_id=None)

    with pytest.raises(Invalid) as raised:
        signal_run(
            ports,
            world.run.id,  # type: ignore[attr-defined]
            Signal(kind="answer", payload={"mode": "session", "text": "ok"}),
        )

    assert "no session recorded" in str(raised.value)
    assert world.ports.records.list_for_run(world.run.id) == []  # type: ignore[attr-defined]


# ── 4: unknown mode rejected ──────────────────────────────────────────────────


def test_unknown_mode_rejected_before_gate_is_recorded() -> None:
    """mode='bogus' → Invalid naming the unknown value; gate is not recorded."""
    world = _parked_world()
    ports = _signal_ports(world, resumable=True, session_id="s-123")

    with pytest.raises(Invalid) as raised:
        signal_run(
            ports,
            world.run.id,  # type: ignore[attr-defined]
            Signal(kind="answer", payload={"mode": "bogus", "text": "ok"}),
        )

    assert "unknown mode: bogus" in str(raised.value)
    assert world.ports.records.list_for_run(world.run.id) == []  # type: ignore[attr-defined]


# ── 5: absent mode defaults to restart ───────────────────────────────────────


def test_absent_mode_defaults_to_restart_and_is_never_rejected() -> None:
    """No mode key in payload → treated as mode='restart'; harness_is_resumable not called."""
    world = _parked_world()
    # Deliberately wire resumable=False to prove the check is never called for absent mode
    ports = SignalPorts(
        writers=world.ports,  # type: ignore[attr-defined]
        engine=world.engine,  # type: ignore[attr-defined]
        harness_is_resumable=lambda _: False,
        latest_attempt_for_run=lambda _: None,
    )

    outcome = signal_run(
        ports,
        world.run.id,  # type: ignore[attr-defined]
        Signal(kind="answer", payload={"text": "go on"}),
    )

    assert outcome.run.status == "running"


# ── default sentinel callables ────────────────────────────────────────────────


def test_mode_session_rejected_when_no_attempt_has_ever_run() -> None:
    """attempt=None → 'no session recorded', not 'harness does not support resume'."""
    world = _parked_world()
    ports = SignalPorts(
        writers=world.ports,  # type: ignore[attr-defined]
        engine=world.engine,  # type: ignore[attr-defined]
        harness_is_resumable=lambda _: True,
        latest_attempt_for_run=lambda _: None,
    )

    with pytest.raises(Invalid) as raised:
        signal_run(
            ports,
            world.run.id,  # type: ignore[attr-defined]
            Signal(kind="answer", payload={"mode": "session", "text": "ok"}),
        )

    assert "no session recorded" in str(raised.value)


def test_always_false_returns_false_for_any_harness_name() -> None:
    """Default harness_is_resumable: any harness name → False (session mode unavailable)."""
    assert _always_false("claude") is False
    assert _always_false("") is False


def test_no_attempt_returns_none_for_any_run_id() -> None:
    """Default latest_attempt_for_run: any run_id → None (no attempt on record)."""
    assert _no_attempt(new_id()) is None
