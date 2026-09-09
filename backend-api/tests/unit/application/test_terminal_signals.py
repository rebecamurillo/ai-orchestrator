"""The three `terminal_*` kinds, now that `handle_signal` applies them (6.7, SPEC CAP-7).

This file is what the retired scope gate leaves behind, and it is deliberately wider than
what it replaces. `test_handle_signal.py` held a parametrized registry asserting that
`terminal_start`, `terminal_release` and `terminal_resume` were each refused
`"{kind} not available yet"`; those three rows are gone (hard rule 1, exception 1), and every
one of them is answered here by its real effect rather than by a refusal. So is the thing the
registry could not say: what each kind does to the Run, what the gate record ends up holding,
and which of them AD-13 refuses and why.

**`_in_scope` itself is gone with them**, together with the router-level illustration
`test_signals_router.py` used it for. It refused nothing once these three landed:
`validate` already refuses `continue` outside `{checkpoint, plan_stale, protected_path}`,
which was the predicate's only conditional arm, so every kind reached it as an unconditional
`True`. `test_the_scope_gate_no_longer_stands_between_a_signal_and_its_effect` below is what
proves the removal was a removal of dead code rather than of a check — it walks every
`SignalKind` and asserts that none of them is answered "not available yet".
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.rules.signals import TERMINAL_RESUMED
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import SIGNAL_KINDS, SignalKind
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
NOT_AVAILABLE = "not available yet"
#: Every kind but `cancel`, which AD-13 admits in every non-terminal status and so cannot
#: illustrate a refusal on a `running` Run.
REFUSED_WHILE_RUNNING = tuple(kind for kind in SIGNAL_KINDS if kind != "cancel")


def parked(park_kind: str, park_path: str, row_status: str, **over: object) -> World:
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {park_path: row_status},
        park_kind=park_kind,
        park_path=park_path,
        park_reason="intent gap",
        **over,
    )


def effect_ports(world: World) -> SignalEffectPorts:
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir="/work",
        read_environment=lambda _run_id: _no_environment(),
    )


def _no_environment() -> RunEnvironment | None:
    """`cancel` is the only kind that reads one, and no test here sends `cancel`."""
    return None


def send(world: World, kind: SignalKind, **payload: object) -> None:
    handle_signal(effect_ports(world), world.run.id, Signal(kind=kind, payload=dict(payload)))


# ── the scope gate is gone, and nothing refuses in its place ─────────────────


@pytest.mark.parametrize("kind", REFUSED_WHILE_RUNNING)
def test_the_scope_gate_no_longer_stands_between_a_signal_and_its_effect(kind: str) -> None:
    """Every kind, against a park that admits none of them: the refusal is always AD-13's own
    sentence, and never the epic-scope one. A kind that had been left out of the retired
    predicate would answer "not available yet" here instead."""
    world = a_world("running", EPIC_PLAN, {})

    with pytest.raises(Conflict) as raised:
        send(world, kind)  # type: ignore[arg-type]

    assert NOT_AVAILABLE not in str(raised.value)
    assert "invalid for status running" in str(raised.value)


# ── terminal_start ───────────────────────────────────────────────────────────


def test_terminal_start_marks_the_session_and_leaves_the_run_parked() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "terminal_start")

    stored = world.stored_run()
    assert stored.terminal_session is True
    assert stored.status == "needs_you"
    assert stored.park_kind == "blocked"
    assert world.status_of(BUILD) == "blocked"


def test_terminal_start_records_the_session_against_the_parked_row() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "terminal_start")

    record = world.records()[-1]
    assert (record.event, record.actor, record.path) == ("terminal_start", "operator", BUILD)
    assert record.text == "terminal session started"


def test_terminal_start_wakes_no_engine_because_nothing_is_running_again() -> None:
    world = parked("blocked", BUILD, "blocked")

    send(world, "terminal_start")

    assert world.engine.calls == []


def test_starting_a_session_twice_is_refused() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    with pytest.raises(Conflict, match="signal terminal_start invalid"):
        send(world, "terminal_start")

    assert world.stored_run().terminal_session is True


def test_a_session_cannot_be_started_on_a_run_that_is_not_parked() -> None:
    """AD-13 gives `terminal_start` the `needs_you` statuses alone: there is no session to
    take over on a Run whose agent is still working."""
    world = a_world("running", EPIC_PLAN, {})

    with pytest.raises(Conflict, match="signal terminal_start invalid for status running"):
        send(world, "terminal_start")


# ── terminal_release ─────────────────────────────────────────────────────────


def test_terminal_release_clears_the_session_and_gives_the_actions_back() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    send(world, "terminal_release")

    stored = world.stored_run()
    assert stored.terminal_session is False
    assert stored.status == "needs_you"
    assert world.records()[-1].text == "terminal session released"


def test_terminal_release_is_admitted_outside_needs_you_too() -> None:
    """AD-13 gives it every non-terminal status: a Run that resumed some other way while the
    Operator still had a terminal open must still be releasable."""
    world = a_world("running", EPIC_PLAN, {}, terminal_session=True)

    send(world, "terminal_release")

    assert world.stored_run().terminal_session is False
    assert world.stored_run().status == "running"
    assert world.engine.calls == []


def test_releasing_a_session_that_was_never_started_is_refused() -> None:
    world = parked("blocked", BUILD, "blocked")

    with pytest.raises(Conflict, match="signal terminal_release invalid"):
        send(world, "terminal_release")


# ── terminal_resume ──────────────────────────────────────────────────────────


def test_terminal_resume_finishes_the_row_and_queues_its_successor() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    send(world, "terminal_resume")

    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"
    stored = world.stored_run()
    assert (stored.status, stored.terminal_session) == ("running", False)
    assert stored.park_kind is None


def test_terminal_resume_records_the_terminal_and_the_evidence() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    send(world, "terminal_resume")

    record = world.records()[-1]
    assert (record.event, record.actor) == ("terminal_resume", "terminal")
    assert record.text == TERMINAL_RESUMED == "story file done and tree clean, resumed by terminal"


def test_terminal_resume_wakes_the_engine_so_the_walk_carries_on() -> None:
    world = parked("blocked", BUILD, "blocked", terminal_session=True)

    send(world, "terminal_resume")

    assert [call[0] for call in world.engine.calls] == ["signal"]


def test_terminal_resume_outside_a_session_is_refused() -> None:
    world = parked("blocked", BUILD, "blocked")

    with pytest.raises(Conflict, match="signal terminal_resume invalid"):
        send(world, "terminal_resume")

    assert world.status_of(BUILD) == "blocked"


@pytest.mark.parametrize(
    ("park_kind", "park_path", "row_status"),
    [("checkpoint", BUILD, "checkpoint"), ("verify_failed", VERIFY, "error")],
    ids=["a checkpoint park", "a verify_failed park"],
)
def test_terminal_resume_only_applies_to_a_blocked_park_on_a_blocked_row(
    park_kind: str, park_path: str, row_status: str
) -> None:
    """AD-13 keys it on both: the poll's own evidence is a Story file the *agent* was asked
    to write, and no other stop is waiting on one."""
    world = parked(park_kind, park_path, row_status, terminal_session=True)

    with pytest.raises(Conflict, match="signal terminal_resume invalid"):
        send(world, "terminal_resume")


def test_a_terminal_resume_that_consumes_the_last_row_ends_the_run() -> None:
    world = a_world(
        "needs_you",
        (("build", "agent"),),
        {"build": "blocked"},
        park_kind="blocked",
        park_path="build",
        park_reason="intent gap",
        terminal_session=True,
    )

    send(world, "terminal_resume")

    assert world.stored_run().status == "done"


# ── the session holds the other actions ──────────────────────────────────────


@pytest.mark.parametrize("kind", ["retry", "skip_story", "skip_epic"])
def test_a_session_refuses_the_actions_the_read_model_stops_offering(kind: str) -> None:
    """The brief's own acceptance criterion is a 409, not a hidden button: a stale tab or a
    script that posts one of these while the Operator is in a terminal must be refused, or
    two writers would be moving the same row (AD-8). AD-13's table cannot say so — it is keyed
    on the park kind and the row's status, and this stop admits all three."""
    world = parked("verify_failed", VERIFY, "error", terminal_session=True)

    with pytest.raises(Conflict, match=f"terminal session in progress: Release it before {kind}"):
        send(world, kind, files=[])  # type: ignore[arg-type]

    assert world.status_of(VERIFY) == "error"
    assert world.records() == []


@pytest.mark.parametrize("kind", ["answer", "continue"])
def test_a_session_refuses_the_two_payload_actions_on_the_park_that_admits_them(
    kind: str,
) -> None:
    """The acceptance criterion names `answer` in particular, and a `blocked` park on an
    `agent` row is exactly where AD-13 would otherwise admit it."""
    world = parked("checkpoint", BUILD, "checkpoint", terminal_session=True)

    with pytest.raises(Conflict, match="terminal session in progress"):
        send(world, kind, text="anything")  # type: ignore[arg-type]

    assert world.status_of(BUILD) == "checkpoint"


def test_answer_on_a_blocked_park_is_refused_only_because_of_the_session() -> None:
    """The control the refusal needs: the same signal on the same stop without a session
    applies, so the 409 above is the session's doing and not the park's."""
    world = parked("blocked", BUILD, "blocked")

    send(world, "answer", text="use the psycopg adapter")

    assert world.status_of(BUILD) == "queued"
    assert world.stored_run().status == "running"


def test_a_session_refuses_a_budget_raise_too_so_the_screen_and_the_server_agree() -> None:
    """`run_admitted_signals` offers only `cancel` and `terminal_release` while a session is
    open, `budget_raise` included — a screen that offers nothing the server would apply is
    the invariant, and it holds in both directions."""
    world = parked("budget", BUILD, "blocked", terminal_session=True, spend_usd=Decimal("41.20"))

    with pytest.raises(Conflict, match="terminal session in progress"):
        send(world, "budget_raise", budget_usd="60.00")

    assert world.stored_run().budget_usd == Decimal("10.00")


def test_release_and_resume_are_the_two_actions_a_session_still_admits() -> None:
    released = parked("blocked", BUILD, "blocked", terminal_session=True)
    send(released, "terminal_release")
    resumed = parked("blocked", BUILD, "blocked", terminal_session=True)
    send(resumed, "terminal_resume")

    assert released.stored_run().terminal_session is False
    assert resumed.status_of(BUILD) == "done"


def test_cancel_still_applies_while_a_session_is_open() -> None:
    """The one action a terminal session never takes away."""
    world = parked("blocked", BUILD, "blocked", terminal_session=True)
    calls: list[UUID] = []
    ports = SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir="/work",
        read_environment=lambda run_id: calls.append(run_id) or None,  # type: ignore[func-returns-value]
    )

    handle_signal(ports, world.run.id, Signal(kind="cancel", payload={"confirm": True}))

    assert world.stored_run().status == "cancelled"
    assert calls == [world.run.id]
    assert Path("/work").name == "work"
