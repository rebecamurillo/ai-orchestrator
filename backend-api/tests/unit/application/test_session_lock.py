"""The senior session's lock (story 2-3, AD-23, AD-13's 2026-11-01 amendment).

While `run.senior_session` is set, every signal but `session_end` and `cancel` is refused —
by `validate` itself, so `signal_run`'s direct callers are refused too — the Run offers only
those two, `PUT /runs/{id}/files` is refused, and a cancel clears the flag.
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules import session as session_rules
from orchestrator.application.rules.signals import (
    SENIOR_SESSION_SIGNALS,
    VALID,
    admitted_signals,
    run_admitted_signals,
    validate,
)
from orchestrator.application.use_cases.run_files import (
    PARKED_REQUIRED,
    RunFilesWritePorts,
    write_run_file,
)
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.statuses import PARK_KINDS, SIGNAL_KINDS, SignalKind
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import (
    BUILD,
    SPEC_FOLDER,
    WORKTREE,
    SessionWorld,
    a_session_world,
)
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.workspace import FakeWorkspace

LOCKED = tuple(kind for kind in SIGNAL_KINDS if kind not in ("cancel", "session_end"))


def locked() -> SessionWorld:
    session = a_session_world()
    session.start()
    return session


def test_the_two_kinds_are_signal_kinds_with_one_rule_each() -> None:
    assert SIGNAL_KINDS[-2:] == ("session_start", "session_end")
    assert VALID["session_start"].operator_action is False
    assert VALID["session_end"].operator_action is False


def test_session_start_is_admitted_on_every_park_but_dependency() -> None:
    assert VALID["session_start"].park_kinds == frozenset(PARK_KINDS) - {"dependency"}
    assert "paused" in VALID["session_start"].park_kinds
    assert VALID["session_end"].park_kinds == frozenset(PARK_KINDS)


def test_neither_kind_is_offered_through_the_stop_table() -> None:
    offered = {kind for park in PARK_KINDS for kind in admitted_signals(park, "agent")}

    assert not offered & {"session_start", "session_end"}


@pytest.mark.parametrize("kind", LOCKED)
def test_every_other_kind_is_refused_while_the_session_is_open(kind: SignalKind) -> None:
    session = locked()
    before = len(session.world.records())

    with pytest.raises(Conflict) as raised:
        session.send(kind)

    assert str(raised.value) == f"senior session open: end it before {kind}"
    assert len(session.world.records()) == before
    assert session.world.stored_run().senior_session is True


def test_a_direct_caller_of_signal_run_is_refused_by_the_lock_too() -> None:
    """The chat reply and `terminal_poll` call `signal_run` without `handle_signal`."""
    session = locked()

    with pytest.raises(Conflict, match="senior session open: end it before answer"):
        signal_run(
            session.ports.signal,
            session.world.run.id,
            Signal(kind="answer", payload={"text": "go"}),
        )


def test_the_lock_is_checked_before_the_table() -> None:
    run = build_run("needs_you", park_kind="budget", park_path=BUILD, senior_session=True)

    with pytest.raises(Conflict, match="senior session open: end it before answer"):
        validate(run, None, Signal(kind="answer"))


def test_cancel_and_session_end_pass_the_lock() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD, senior_session=True)

    assert validate(run, None, Signal(kind="cancel")) is VALID["cancel"]
    assert validate(run, None, Signal(kind="session_end")) is VALID["session_end"]


def test_an_open_session_offers_cancel_and_session_end_only() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD, senior_session=True)

    assert run_admitted_signals(run, "agent") == ("cancel", "session_end")
    assert SENIOR_SESSION_SIGNALS == ("cancel", "session_end")


def test_the_session_set_wins_over_a_terminal_session_flag() -> None:
    run = build_run("needs_you", park_kind="blocked", senior_session=True, terminal_session=True)

    assert run_admitted_signals(run, "agent") == SENIOR_SESSION_SIGNALS


def test_a_terminal_run_offers_nothing_even_with_the_flag_set() -> None:
    assert run_admitted_signals(build_run("failed", senior_session=True), None) == ()


def test_after_session_end_the_stop_offers_its_own_set_again() -> None:
    session = locked()
    rows = session.world.ports.steps.list_for_run(session.world.run.id)
    assert run_admitted_signals(session.world.stored_run(), "agent", rows=rows) == (
        "cancel",
        "session_end",
    )

    session.send("session_end")

    stored = session.world.stored_run()
    assert run_admitted_signals(stored, "agent", rows=rows) == (
        "answer",
        "skip_step",
        "skip_story",
        "skip_epic",
        "cancel",
    )


def test_cancel_clears_the_flag() -> None:
    session = locked()

    session.send("cancel")

    stored = session.world.stored_run()
    assert stored.status == "cancelled"
    assert stored.senior_session is False


def test_terminal_start_requires_no_senior_session() -> None:
    rule = VALID["terminal_start"]
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD)
    assert rule.extra is not None

    assert rule.extra(run, None, Signal(kind="terminal_start"), ()) is True
    locked_run = run.model_copy(update={"senior_session": True})
    assert rule.extra(locked_run, None, Signal(kind="terminal_start"), ()) is False
    busy = run.model_copy(update={"terminal_session": True})
    assert rule.extra(busy, None, Signal(kind="terminal_start"), ()) is False


def test_the_predicates_read_the_two_flags() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD)
    signal = Signal(kind="session_start")

    assert session_rules.can_start_session(run, None, signal, ()) is True
    assert session_rules.in_senior_session(run, None, signal, ()) is False
    assert session_rules.in_terminal_session(run, None, signal, ()) is False
    no_path = run.model_copy(update={"park_path": None})
    assert session_rules.can_start_session(no_path, None, signal, ()) is False


# ── the race: session_start and terminal_start sent together ─────────────────


def test_session_start_then_terminal_start_refuses_the_second() -> None:
    session = locked()

    with pytest.raises(Conflict):
        session.send("terminal_start")

    assert session.world.stored_run().terminal_session is False


def test_terminal_start_then_session_start_refuses_the_second() -> None:
    session = a_session_world()
    session.send("terminal_start")

    with pytest.raises(Conflict, match="invalid for status needs_you"):
        session.start()

    assert session.world.stored_run().senior_session is False


def test_two_signals_that_both_passed_the_early_read_serialise_on_the_row_lock() -> None:
    """Both read the unlocked Run and pass; `signal_run` re-reads it under the lock, so the
    one that commits second sees the first one's flag and is refused."""
    session = a_session_world()
    run = session.world.stored_run()
    rows = session.world.ports.steps.list_for_run(run.id)
    start = Signal(kind="session_start", payload={"scope": "story", "harness": "claude"})
    terminal = Signal(kind="terminal_start")
    validate(run, session.world.row(BUILD), start, rows)
    validate(run, session.world.row(BUILD), terminal, rows)
    calls = session.world.ports.runs.calls

    signal_run(session.ports.signal, run.id, start)
    with pytest.raises(Conflict):
        signal_run(session.ports.signal, run.id, terminal)

    assert calls.count(("get_for_update", run.id)) == 2  # noqa: PLR2004 — one per signal
    stored = session.world.stored_run()
    assert (stored.senior_session, stored.terminal_session) == (True, False)


# ── PUT /runs/{id}/files ─────────────────────────────────────────────────────


def test_an_operator_file_edit_is_refused_while_the_session_is_open() -> None:
    session = locked()
    path = f"{SPEC_FOLDER}/stories/1-answer.md"
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = RunFilesWritePorts(
        runs=session.world.ports.runs,
        workspace=lambda _root: FakeWorkspace(WORKTREE, {path: "before"}),
        git=FakeGit(),
        records=session.world.ports.records,
        clock=FakeClock(EPOCH),
        uow=uow,
    )

    with pytest.raises(Conflict) as raised:
        write_run_file(ports, session.world.run.id, path, "after")

    assert str(raised.value) == PARKED_REQUIRED


def test_a_file_edit_racing_a_session_start_is_refused_under_the_row_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unlocked read still sees the stop as it was before `session_start` committed;
    the read under the lock sees the flag, and nothing is written or committed."""
    session = locked()
    stale = session.world.stored_run().model_copy(update={"senior_session": False})
    runs = session.world.ports.runs
    monkeypatch.setattr(runs, "get", lambda _run_id: stale)
    path = f"{SPEC_FOLDER}/stories/1-answer.md"
    workspace = FakeWorkspace(WORKTREE, {path: "before"})
    git = FakeGit()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = RunFilesWritePorts(
        runs=runs,
        workspace=lambda _root: workspace,
        git=git,
        records=session.world.ports.records,
        clock=FakeClock(EPOCH),
        uow=uow,
    )
    records = len(session.world.records())

    with pytest.raises(Conflict) as raised:
        write_run_file(ports, session.world.run.id, path, "after")

    assert str(raised.value) == PARKED_REQUIRED
    assert ("get_for_update", session.world.run.id) in runs.calls
    assert workspace.read(path) == "before"
    assert git.called("commit") == []
    assert len(session.world.records()) == records


def test_a_run_gone_by_the_locked_read_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = a_session_world()
    runs = session.world.ports.runs
    monkeypatch.setattr(runs, "get_for_update", lambda _run_id: None)
    path = f"{SPEC_FOLDER}/stories/1-answer.md"
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = RunFilesWritePorts(
        runs=runs,
        workspace=lambda _root: FakeWorkspace(WORKTREE, {path: "before"}),
        git=FakeGit(),
        records=session.world.ports.records,
        clock=FakeClock(EPOCH),
        uow=uow,
    )

    with pytest.raises(NotFound):
        write_run_file(ports, session.world.run.id, path, "after")
