"""The value objects executors, the planner and signals speak in (`domain/values.py`).

They carry no behaviour, so what there is to check is exactly what a later story is
entitled to assume: every one is frozen, so an executor cannot edit the result it returned;
the optional halves of a `StepResult` default to `None`, so a plain success needs no
keywords it has nothing to say with; and a `Signal` with no payload still has a mapping to
read rather than a `None` every caller would have to guard.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.domain.values import (
    Park,
    PlannedRow,
    Redispatch,
    Signal,
    StepResult,
    Worktree,
)


def a_planned_row(**overrides: object) -> PlannedRow:
    fields: dict[str, object] = {
        "seq": 1,
        "path": "steps[0]",
        "label": "worktree",
        "kind": "git.worktree",
        "gate": "deterministic",
        "status": "planned",
        "reason": None,
        "with_resolved": {"base": "main"},
        "frame": None,
        "story_id": None,
    }
    fields.update(overrides)
    return PlannedRow(**fields)  # type: ignore[arg-type]


def a_worktree() -> Worktree:
    return Worktree(branch="story/4-1", path="/work/wt/4-1", created_branch=True, pushed=False)


# ── Park ─────────────────────────────────────────────────────────────────────


def test_a_park_names_a_kind_and_a_reason() -> None:
    park = Park(kind="blocked", reason="the agent asked a question")

    assert (park.kind, park.reason) == ("blocked", "the agent asked a question")


def test_a_park_has_no_path_until_one_is_given() -> None:
    assert Park(kind="budget", reason="over budget").path is None


def test_a_park_carries_the_path_it_stopped_at() -> None:
    park = Park(kind="protected_path", reason="tests/unit/x.py", path="steps[2]")

    assert park.path == "steps[2]"


# ── Redispatch ───────────────────────────────────────────────────────────────


def test_a_redispatch_names_the_row_to_go_back_to_and_its_bound() -> None:
    bound = 3
    redispatch = Redispatch(target_seq=4, max=bound)

    assert redispatch.target_seq == 4  # noqa: PLR2004 — the seq is the literal under test
    assert redispatch.max == bound


# ── StepResult ───────────────────────────────────────────────────────────────


def test_a_plain_success_needs_only_a_status_and_a_gate() -> None:
    result = StepResult(status="done", gate="deterministic")

    assert result.output_ref is None
    assert result.park is None
    assert result.redispatch is None
    assert result.reason is None


def test_a_result_carries_the_park_that_stops_the_run() -> None:
    park = Park(kind="checkpoint", reason="review the diff")

    result = StepResult(status="checkpoint", gate="human", park=park, reason="review the diff")

    assert result.park == park
    assert result.reason == "review the diff"


def test_a_result_carries_a_redispatch_and_an_output_reference() -> None:
    result = StepResult(
        status="done",
        gate="liveness",
        output_ref="/work/logs/1.log",
        redispatch=Redispatch(target_seq=2, max=1),
    )

    assert result.output_ref == "/work/logs/1.log"
    assert result.redispatch is not None
    assert result.redispatch.target_seq == 2  # noqa: PLR2004 — the seq under test


def test_a_result_refuses_a_status_outside_the_step_alphabet() -> None:
    with pytest.raises(ValidationError):
        StepResult(status="needs_you", gate="human")  # type: ignore[arg-type]


def test_a_result_refuses_a_gate_outside_the_four() -> None:
    with pytest.raises(ValidationError):
        StepResult(status="done", gate="green")  # type: ignore[arg-type]


def test_a_result_accepts_the_unvalidated_gate() -> None:
    """The planner records it for a step whose Template declared no gate (NFR-2)."""
    assert StepResult(status="done", gate="unvalidated").gate == "unvalidated"


# ── Signal ───────────────────────────────────────────────────────────────────


def test_a_signal_with_nothing_to_say_still_has_a_payload_to_read() -> None:
    assert Signal(kind="continue").payload == {}


def test_a_signal_carries_the_payload_the_operator_submitted() -> None:
    signal = Signal(kind="answer", payload={"text": "use the second option"})

    assert signal.payload == {"text": "use the second option"}


def test_a_signal_refuses_a_kind_ad_13_does_not_name() -> None:
    with pytest.raises(ValidationError):
        Signal(kind="park")  # type: ignore[arg-type]


def test_two_signals_do_not_share_one_payload() -> None:
    """A mutable default shared between instances would leak one Run's answer into another."""
    first = Signal(kind="continue")
    second = Signal(kind="continue")

    assert first.payload is not second.payload


# ── PlannedRow ───────────────────────────────────────────────────────────────


def test_a_planned_row_carries_every_column_the_planner_fills() -> None:
    row = a_planned_row(frame="steps[3].stories[0]", story_id="4-1")

    assert row.seq == 1
    assert row.path == "steps[0]"
    assert row.label == "worktree"
    assert row.kind == "git.worktree"
    assert row.gate == "deterministic"
    assert row.status == "planned"
    assert row.reason is None
    assert row.with_resolved == {"base": "main"}
    assert row.frame == "steps[3].stories[0]"
    assert row.story_id == "4-1"


def test_a_planned_row_takes_any_kind_because_the_registry_is_the_enumeration() -> None:
    """`domain/` may not import `application/steps`, so `kind` is a plain string here."""
    assert a_planned_row(kind="bmad.install").kind == "bmad.install"


def test_a_planned_row_refuses_a_status_outside_the_step_alphabet() -> None:
    with pytest.raises(ValidationError):
        a_planned_row(status="needs_you")


# ── Worktree ─────────────────────────────────────────────────────────────────


def test_a_worktree_records_its_branch_path_and_what_happened_to_it() -> None:
    worktree = a_worktree()

    assert worktree.branch == "story/4-1"
    assert worktree.path == "/work/wt/4-1"
    assert worktree.created_branch is True
    assert worktree.pushed is False


# ── frozen ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (Park(kind="budget", reason="over"), "reason"),
        (Redispatch(target_seq=1, max=1), "max"),
        (StepResult(status="done", gate="human"), "status"),
        (Signal(kind="cancel"), "kind"),
        (a_planned_row(), "seq"),
        (a_worktree(), "pushed"),
    ],
    ids=["park", "redispatch", "step_result", "signal", "planned_row", "worktree"],
)
def test_every_value_object_is_frozen(value: object, field: str) -> None:
    with pytest.raises(ValidationError):
        setattr(value, field, None)
