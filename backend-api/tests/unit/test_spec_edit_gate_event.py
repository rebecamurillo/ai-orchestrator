"""`spec_edit` (story 6-3): a third, outer layer of the gate-record alphabet beside AD-8's
three and AD-9's two — a direct worktree write outside `signal_run`, the brief's own words
"the only worktree writes outside an engine step besides cancel".

`tests/unit/test_gate_events.py` (story 4-5) pins `ALL_GATE_EVENTS == (*GATE_EVENTS,
*MACHINE_EVENTS)` exactly, so this module proves the honest alternative that story's Design
Notes describe: `spec_edit` widens the `GateEvent` **type** so `GateRecord(event=
"spec_edit", ...)` validates, while `ALL_GATE_EVENTS`'s own **value** stays untouched. No
existing test file is edited for this.
"""

from __future__ import annotations

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import ALL_GATE_EVENTS, GATE_EVENTS, MACHINE_EVENTS, WRITE_EVENTS
from tests.unit.fakes.clock import EPOCH


def a_record(event: str) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=new_id(),
        at=EPOCH,
        event=event,  # type: ignore[arg-type]
        actor="operator",
    )


def test_spec_edit_is_the_one_write_event() -> None:
    assert WRITE_EVENTS == ("spec_edit",)


def test_a_gate_record_accepts_spec_edit() -> None:
    record = a_record("spec_edit")

    assert record.event == "spec_edit"
    assert record.actor == "operator"


def test_all_gate_events_stays_exactly_ad_8s_three_plus_ad_9s_two() -> None:
    """The value this story's brief says not to touch — `spec_edit` is not in it."""
    assert ALL_GATE_EVENTS == (*GATE_EVENTS, *MACHINE_EVENTS)
    assert "spec_edit" not in ALL_GATE_EVENTS
