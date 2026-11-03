"""`pause_resume`: whether a resume signal lifted a pause, read off the gate records.

A `continue` that resumed a pause is not the `continue` that approves a spec checkpoint or a
stale plan, so the row that runs next must not be handed it as a resume signal."""

from __future__ import annotations

from orchestrator.application.use_cases.pause_resume import resumed_a_pause
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import EPOCH


def line(event: str, **over: object) -> GateRecord:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "at": EPOCH,
        "event": event,
        "actor": "operator",
        "text": "",
    }
    fields.update(over)
    return GateRecord(**fields)  # type: ignore[arg-type]


def test_a_continue_after_a_pause_resumed_it() -> None:
    park, resume = line("paused", actor="machine"), line("continue")

    assert resumed_a_pause([park, resume], resume)


def test_records_between_the_pause_and_the_continue_do_not_hide_it() -> None:
    park, edit, resume = line("paused", actor="machine"), line("spec_edit"), line("continue")

    assert resumed_a_pause([park, edit, resume], resume)


def test_a_continue_after_any_other_stop_did_not() -> None:
    park, resume = line("checkpoint", actor="machine"), line("continue")

    assert not resumed_a_pause([park, resume], resume)


def test_the_stop_that_counts_is_the_latest_one_before_the_record() -> None:
    paused, later, resume = line("paused"), line("plan_stale"), line("continue")

    assert not resumed_a_pause([paused, later, resume], resume)


def test_a_record_with_no_stop_before_it_resumed_nothing() -> None:
    resume = line("continue")

    assert not resumed_a_pause([line("start"), resume], resume)


def test_a_later_stop_is_not_the_one_the_record_answered() -> None:
    resume, later = line("continue"), line("paused")

    assert not resumed_a_pause([resume, later], resume)
