"""The gate-record alphabet, including the two events that are not Run transitions.

`tests/unit/test_run_statuses.py` pins `GATE_EVENTS` — AD-8's three alphabets, the events a
`gate_record` carries for a Run *transition*. AD-9 has two more that no Run transition
accompanies: a bounded re-execution "is a recorded `attempt` + `gate_record`" while the Run
stays exactly where it was. `apply_step_result` writes `redispatch` today; `retry_auto` is
Epic 5's template retry and is declared with it so the alphabet does not move twice.

This module is what pins that second half: without it `MachineEvent`, `MACHINE_EVENTS` and
`ALL_GATE_EVENTS` would be three public names in `domain/statuses.py` that no assertion
holds, and re-narrowing the union would break nothing until Epic 5 tried to record a retry.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import (
    ALL_GATE_EVENTS,
    GATE_EVENTS,
    LIFECYCLE_EVENTS,
    MACHINE_EVENTS,
    PARK_KINDS,
    SIGNAL_KINDS,
)
from tests.unit.fakes.clock import EPOCH


def a_record(event: str) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=new_id(),
        at=EPOCH,
        event=event,  # type: ignore[arg-type]
        actor="machine",
    )


def test_the_machine_events_are_ad_9s_two_bounded_re_executions() -> None:
    assert MACHINE_EVENTS == ("redispatch", "retry_auto")


def test_the_whole_alphabet_is_ad_8s_three_plus_ad_9s_two() -> None:
    assert ALL_GATE_EVENTS == (*GATE_EVENTS, *MACHINE_EVENTS)
    assert GATE_EVENTS == (*PARK_KINDS, *SIGNAL_KINDS, *LIFECYCLE_EVENTS)


def test_the_transition_alphabet_is_a_strict_subset_of_the_whole_one() -> None:
    """`GATE_EVENTS` keeps its narrower meaning; nothing reads it as the full set."""
    assert set(GATE_EVENTS) < set(ALL_GATE_EVENTS)


@pytest.mark.parametrize("event", ALL_GATE_EVENTS)
def test_a_gate_record_accepts_every_event_of_the_whole_alphabet(event: str) -> None:
    assert a_record(event).event == event


def test_a_gate_record_still_refuses_a_word_no_alphabet_names() -> None:
    """`expired` is not one: AD-13 applies the 30-day `recv` expiry as Run `failed`."""
    for word in ("park", "expired", "redispatched"):
        with pytest.raises(ValidationError):
            a_record(word)
