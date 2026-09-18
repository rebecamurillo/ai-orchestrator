"""The two state machines of AD-8, checked over the whole product of statuses and events.

The tables in `domain/statuses.py` are the only encoding of AD-8's two diagrams, so a test
that read them and then asserted the function agrees with them would prove nothing about
the diagrams. The two dictionaries below are a second, independent transcription of the
brief's two tables; the tables under test are asserted equal to them, and only then is the
product of every status by every event walked — a listed pair returns its target, and every
other pair raises `InvalidTransition` naming both tokens, which is what makes an unlisted
transition a bug a caller can read rather than a silent `None`.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.errors import DomainError
from orchestrator.domain.statuses import (
    ACTORS,
    GATE_EVENTS,
    GATES,
    LIFECYCLE_EVENTS,
    PARK_KINDS,
    RUN_EVENTS,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    SIGNAL_KINDS,
    STEP_EVENTS,
    STEP_STATUSES,
    STEP_TRANSITIONS,
    TERMINAL_RUN,
    InvalidTransition,
    RunEvent,
    RunStatus,
    StepEvent,
    StepStatus,
    run_transition,
    step_transition,
)

#: AD-8's Run diagram, transcribed here a second time so the module under test is compared
#: against the spine rather than against itself.
EXPECTED_RUN: dict[tuple[RunStatus, RunEvent], RunStatus] = {
    ("queued", "start"): "running",
    ("queued", "cancel"): "cancelled",
    ("running", "park"): "needs_you",
    ("running", "finish"): "done",
    ("running", "fail"): "failed",
    ("running", "cancel"): "cancelled",
    ("needs_you", "answer"): "running",
    ("needs_you", "continue"): "running",
    ("needs_you", "retry"): "running",
    ("needs_you", "skip_story"): "running",
    ("needs_you", "skip_epic"): "running",
    ("needs_you", "budget_raise"): "running",
    ("needs_you", "terminal_resume"): "running",
    ("needs_you", "expire"): "failed",
    ("needs_you", "cancel"): "cancelled",
}

#: AD-8's Step diagram, transcribed the same way.
EXPECTED_STEP: dict[tuple[StepStatus, StepEvent], StepStatus] = {
    ("planned", "predecessor_done"): "queued",
    ("planned", "skip"): "skipped",
    ("queued", "start"): "running",
    ("queued", "skip"): "skipped",
    ("running", "done"): "done",
    ("running", "blocked"): "blocked",
    ("running", "checkpoint"): "checkpoint",
    ("running", "error"): "error",
    ("done", "redispatch"): "queued",
    ("blocked", "answer"): "queued",
    ("blocked", "terminal_resume"): "done",
    ("blocked", "skip"): "skipped",
    ("checkpoint", "continue"): "queued",
    ("checkpoint", "continue_checkpoint"): "done",
    ("checkpoint", "skip"): "skipped",
    ("error", "retry"): "queued",
    ("error", "continue_accept"): "running",
    ("error", "skip"): "skipped",
}


# ── the token alphabets ──────────────────────────────────────────────────────


def test_the_run_status_tokens_are_the_ones_the_conventions_spell() -> None:
    """`needs_you` is stored as written; the UI maps it to `BLK`/`CHK`, nothing renames it."""
    assert RUN_STATUSES == ("queued", "running", "needs_you", "done", "failed", "cancelled")


def test_the_step_status_tokens_are_the_ones_the_conventions_spell() -> None:
    assert STEP_STATUSES == (
        "planned",
        "queued",
        "running",
        "done",
        "blocked",
        "checkpoint",
        "error",
        "skipped",
    )


def test_the_park_kinds_are_the_ten_the_brief_lists() -> None:
    assert PARK_KINDS == (
        "blocked",
        "checkpoint",
        "verify_failed",
        "budget",
        "timeout",
        "push_rejected",
        "protected_path",
        "misconfigured",
        "plan_stale",
        "internal",
    )


def test_the_signal_kinds_are_the_eleven_ad_13_names() -> None:
    # operator revision 2026-09-18: "start" added for the deferred-start signal (story 5-3);
    # anchor exception 4 granted 2026-09-18T13:17:20Z.
    assert SIGNAL_KINDS == (
        "answer",
        "continue",
        "retry",
        "skip_story",
        "skip_epic",
        "budget_raise",
        "cancel",
        "terminal_start",
        "terminal_release",
        "terminal_resume",
        "start",
    )


def test_the_domain_gate_carries_unvalidated_as_well() -> None:
    """The template-declarable subset has three; the planner records a fourth (NFR-2)."""
    assert GATES == ("liveness", "deterministic", "human", "unvalidated")


def test_the_actors_are_the_three_a_gate_record_can_name() -> None:
    assert ACTORS == ("operator", "machine", "terminal")


def test_a_gate_event_is_a_park_kind_a_signal_kind_or_a_lifecycle_event() -> None:
    # operator revision 2026-09-18: "started_by_operator" added to LifecycleEvent for
    # the deferred-start gate record (story 5-3); anchor exception 4 granted 2026-09-18T13:17:20Z.
    assert LIFECYCLE_EVENTS == ("start", "done", "failed", "cancelled", "started_by_operator")
    assert GATE_EVENTS == (*PARK_KINDS, *SIGNAL_KINDS, *LIFECYCLE_EVENTS)


def test_the_terminal_run_statuses_accept_nothing() -> None:
    assert TERMINAL_RUN == frozenset({"done", "failed", "cancelled"})
    for status in TERMINAL_RUN:
        assert not [pair for pair in RUN_TRANSITIONS if pair[0] == status]


# ── the tables ───────────────────────────────────────────────────────────────


def test_the_run_table_is_ad_8s_run_diagram() -> None:
    assert RUN_TRANSITIONS == EXPECTED_RUN


def test_the_step_table_is_ad_8s_step_diagram() -> None:
    assert STEP_TRANSITIONS == EXPECTED_STEP


def test_every_run_pair_in_the_table_uses_declared_tokens() -> None:
    for (status, event), target in RUN_TRANSITIONS.items():
        assert status in RUN_STATUSES
        assert event in RUN_EVENTS
        assert target in RUN_STATUSES


def test_every_step_pair_in_the_table_uses_declared_tokens() -> None:
    for (status, event), target in STEP_TRANSITIONS.items():
        assert status in STEP_STATUSES
        assert event in STEP_EVENTS
        assert target in STEP_STATUSES


# ── the full product ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("event", RUN_EVENTS)
@pytest.mark.parametrize("status", RUN_STATUSES)
def test_a_run_pair_is_its_target_or_a_named_refusal(status: RunStatus, event: RunEvent) -> None:
    expected = EXPECTED_RUN.get((status, event))
    if expected is None:
        with pytest.raises(InvalidTransition) as error:
            run_transition(status, event)
        assert status in str(error.value)
        assert event in str(error.value)
    else:
        assert run_transition(status, event) == expected


@pytest.mark.parametrize("event", STEP_EVENTS)
@pytest.mark.parametrize("status", STEP_STATUSES)
def test_a_step_pair_is_its_target_or_a_named_refusal(status: StepStatus, event: StepEvent) -> None:
    expected = EXPECTED_STEP.get((status, event))
    if expected is None:
        with pytest.raises(InvalidTransition) as error:
            step_transition(status, event)
        assert status in str(error.value)
        assert event in str(error.value)
    else:
        assert step_transition(status, event) == expected


# ── the rows the I/O matrix names by hand ────────────────────────────────────


def test_a_queued_run_starts() -> None:
    assert run_transition("queued", "start") == "running"


def test_a_checkpoint_row_continues_to_done() -> None:
    assert step_transition("checkpoint", "continue_checkpoint") == "done"


def test_an_agent_row_at_a_checkpoint_continues_to_queued() -> None:
    assert step_transition("checkpoint", "continue") == "queued"


@pytest.mark.parametrize("event", RUN_EVENTS)
def test_a_done_run_accepts_no_event_at_all(event: RunEvent) -> None:
    with pytest.raises(InvalidTransition) as error:
        run_transition("done", event)

    assert "done" in str(error.value)
    assert event in str(error.value)


def test_invalid_transition_is_not_a_domain_error() -> None:
    """An unlisted transition is a bug, not an outcome `api/errors.py` maps to a status."""
    assert not issubclass(InvalidTransition, DomainError)
    assert issubclass(InvalidTransition, Exception)
