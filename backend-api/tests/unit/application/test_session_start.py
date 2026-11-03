"""`session_start {scope, harness, model}` (story 2-3, AD-23, AD-10's 2026-11-02 amendment).

A start at a stop sets `run.senior_session` and records the payload, and changes no status.
Every refusal writes nothing and names its reason.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.harness import ProbeResult
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import (
    BUILD,
    MODEL,
    SessionWorld,
    a_session_world,
    probing,
)
from tests.unit.application.writer_fixtures import INITIATIVE_PLAN

PROBE_FAILS = ProbeResult(ok=False, failing_reason="not logged in", version="", models=[])
PROBE_SILENT = ProbeResult(ok=False, failing_reason=None, version="", models=[])
EPIC_BUILD = "epics[0].stories[0].build"
#: `probing()` scripts four answers; one start reads one.
PROBES_LEFT = 3


def refused(session: SessionWorld, error: type[Exception], **payload: object) -> str:
    before = (session.world.stored_run(), len(session.world.records()))
    fields = {"scope": "story", "harness": "claude", "model": MODEL}
    fields.update(payload)

    with pytest.raises(error) as raised:
        session.send("session_start", **fields)

    assert (session.world.stored_run(), len(session.world.records())) == before
    return str(raised.value)


def test_a_start_at_a_blocked_stop_opens_the_session() -> None:
    session = a_session_world()

    outcome = session.start()

    stored = session.world.stored_run()
    assert stored.senior_session is True
    assert (stored.status, stored.park_kind, stored.park_path) == ("needs_you", "blocked", BUILD)
    assert session.world.status_of(BUILD) == "blocked"
    assert outcome.resumed is False
    assert session.world.engine.calls == []
    record = session.world.records()[-1]
    assert (record.event, record.actor, record.path) == ("session_start", "operator", BUILD)
    assert record.payload == {"scope": "story", "harness": "claude", "model": MODEL}
    assert record.text == "senior session started"


def test_the_probe_is_re_read_once_per_start() -> None:
    session = a_session_world()

    session.start()

    assert len(session.harnesses["claude"]._probe_queue) == PROBES_LEFT


def test_a_paused_stop_admits_a_start() -> None:
    session = a_session_world(
        park_kind="paused", park_path="stories[0].verify", row_status="planned"
    )

    session.start(scope="run")

    assert session.world.stored_run().senior_session is True


def test_a_run_scope_needs_no_frame() -> None:
    session = a_session_world(park_kind="plan_stale", park_path="plan", row_status="error")

    session.start(scope="run")

    assert session.world.stored_run().senior_session is True


def test_an_epic_scope_passes_on_an_epic_frame() -> None:
    session = a_session_world(plan=INITIATIVE_PLAN, park_path=EPIC_BUILD)

    session.start(scope="epic")

    assert session.world.stored_run().senior_session is True


def test_an_epic_scope_passes_on_a_run_that_is_one_epic() -> None:
    session = a_session_world()

    session.start(scope="epic")

    assert session.world.stored_run().senior_session is True


def test_a_model_the_gateway_lists_none_of_passes_as_create_run_lets_it() -> None:
    empty = ProbeResult(ok=True, failing_reason=None, version="1.0.0", models=[])
    session = a_session_world(harnesses={"claude": probing(empty)})

    session.start(model="anything")

    assert session.world.stored_run().senior_session is True


# ── refusals ─────────────────────────────────────────────────────────────────


def test_a_terminal_session_refuses_a_start() -> None:
    message = refused(a_session_world(terminal_session=True), Conflict)

    assert "signal session_start invalid for status needs_you" in message


def test_an_open_session_refuses_a_second_start() -> None:
    session = a_session_world()
    session.start()

    assert refused(session, Conflict) == "senior session open: end it before session_start"


def test_a_dependency_stop_refuses_a_start() -> None:
    session = a_session_world(park_kind="dependency", park_path=None)

    assert "park dependency" in refused(session, Conflict)


def test_a_running_run_refuses_a_start() -> None:
    session = a_session_world(park_kind=None, park_path=None)
    session.world.ports.runs.update(session.world.run.model_copy(update={"status": "running"}))

    assert "invalid for status running" in refused(session, Conflict)


def test_a_story_scope_outside_a_story_frame_is_refused() -> None:
    session = a_session_world(park_kind="plan_stale", park_path="plan", row_status="error")

    assert refused(session, Invalid) == "no story frame at plan"


def test_an_epic_scope_outside_any_epic_is_refused() -> None:
    session = a_session_world(plan=INITIATIVE_PLAN, park_path="plan", row_status="error")

    assert refused(session, Invalid, scope="epic") == "no epic frame at plan"


def test_an_unknown_scope_is_refused() -> None:
    message = refused(a_session_world(), Invalid, scope="galaxy")

    assert message == "unknown scope galaxy: one of story, epic, run"


def test_an_unknown_harness_is_refused() -> None:
    assert refused(a_session_world(), Invalid, harness="vim") == "unknown harness vim"


def test_a_harness_that_cannot_resume_is_refused() -> None:
    session = a_session_world(harnesses={"claude": probing(resume=False)})

    assert refused(session, Invalid) == "harness claude cannot resume a session"


def test_a_failing_probe_is_refused_with_its_reason() -> None:
    session = a_session_world(harnesses={"claude": probing(PROBE_FAILS)})

    assert refused(session, Invalid) == "not logged in"


def test_a_failing_probe_without_a_reason_still_says_so() -> None:
    session = a_session_world(harnesses={"claude": probing(PROBE_SILENT)})

    assert refused(session, Invalid) == "probe failed"


def test_an_unlisted_model_is_refused_naming_the_list() -> None:
    message = refused(a_session_world(), Invalid, model="gpt-9")

    assert message == f"model 'gpt-9' not in probed list: ['{MODEL}']"


def test_no_worktree_is_refused() -> None:
    assert refused(a_session_world(worktree_path=None), Conflict) == "no worktree yet"


def test_no_remaining_budget_is_refused() -> None:
    session = a_session_world(budget_usd=Decimal("5.00"), spend_usd=Decimal("5.00"))

    assert refused(session, Conflict) == "no remaining budget"


def test_an_unlimited_budget_never_refuses() -> None:
    session = a_session_world(budget_usd=None, spend_usd=Decimal("500.00"))

    session.start()

    assert session.world.stored_run().senior_session is True


def test_no_preflight_wired_means_no_harness_is_known() -> None:
    session = a_session_world()
    ports = session.ports
    bare = SignalEffectPorts(
        signal=SignalPorts(writers=ports.signal.writers, engine=ports.signal.engine),
        git=ports.git,
        process=ports.process,
        work_dir=ports.work_dir,
        read_environment=ports.read_environment,
    )
    signal = Signal(kind="session_start", payload={"scope": "story", "harness": "claude"})
    with pytest.raises(Invalid, match="unknown harness claude"):
        handle_signal(bare, session.world.run.id, signal)
