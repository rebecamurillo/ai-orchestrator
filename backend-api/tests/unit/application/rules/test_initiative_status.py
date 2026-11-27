"""The initiative status, one row per line of the table (epic 7 story 2, SPEC CAP-2; AD-36)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import (
    RunFacts,
    StatusReading,
    initiative_status,
)
from orchestrator.domain.entities.initiative import FrozenWorkflow
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from tests.unit.initiative_fixtures import a_run, a_sequence, an_initiative

MAPPING = {"final": "done"}
NOW = datetime(2026, 11, 25, tzinfo=UTC)
NOT_CLOSED = "step not closed · PRD.md has status draft, the done content is status final"


def _facts(
    attention: Attention | None = None,
    step: str | None = None,
    word: str | None = None,
    **run: Any,
) -> RunFacts:
    run.setdefault("initiative_position", 0)
    return RunFacts(run=a_run(**run), attention=attention, step=step, step_word=word)


def _read(*runs: RunFacts, advances: tuple[InitiativeAdvance, ...] = (), **init: Any) -> Any:
    return initiative_status(an_initiative(**init), runs, advances, MAPPING)


def _advance(**overrides: Any) -> InitiativeAdvance:
    values: dict[str, Any] = {
        "id": new_id(),
        "initiative_id": new_id(),
        "from_run_id": new_id(),
        "round": 1,
        "position": 1,
    }
    values.update(overrides)
    return InitiativeAdvance(**values)


def _is(reading: StatusReading, status: str, reason: str = "") -> None:
    assert (reading.status, reading.reason) == (status, reason)


def test_row_1_cancelled_wins_over_merged() -> None:
    _is(_read(cancelled_at=NOW, pr_merged_at=NOW), "cancelled")


def test_row_2_merged_is_done() -> None:
    _is(_read(_facts(status="running"), pr_merged_at=NOW), "done")


def test_row_3_unconsumed_blocked_advance_waits_for_her() -> None:
    advance = _advance(blocked_reason="no project budget")
    _is(
        _read(_facts(status="running"), advances=(advance,)), "waiting for her", "no project budget"
    )


def test_row_3_consumed_blocked_advance_is_ignored() -> None:
    advance = _advance(blocked_reason="no project budget", consumed_at=NOW)
    _is(_read(_facts(status="running"), advances=(advance,)), "running")


def test_row_4_queued_run() -> None:
    _is(_read(_facts(status="queued")), "running", "waiting for a slot")


def test_row_4_running_with_mapped_word() -> None:
    _is(_read(_facts(status="running", word="final")), "running")


def test_row_4_running_without_word() -> None:
    _is(_read(_facts(status="running")), "running")


def test_row_4_running_with_unmapped_word_fails() -> None:
    _is(_read(_facts(status="running", word="drafted")), "failed", "unmapped word drafted")


def test_row_5_conversation_blocked_by_unclosed_step() -> None:
    facts = _facts("blocked", status="needs_you", park_kind="conversation", park_reason=NOT_CLOSED)
    _is(_read(facts), "waiting for her", NOT_CLOSED)


def test_row_5_conversation_blocked_for_another_reason_has_no_reason() -> None:
    facts = _facts(
        "blocked", status="needs_you", park_kind="conversation", park_reason="agent error"
    )
    _is(_read(facts), "waiting for her")


def test_row_6_her_turn_answering_and_queued_read_running() -> None:
    for attention in ("your_turn", "answering", "queued"):
        facts = _facts(attention, status="needs_you", park_kind="conversation")  # type: ignore[arg-type]
        _is(_read(facts), "running")


def test_row_7_other_stop_waits_for_her() -> None:
    facts = _facts("blocked", status="needs_you", park_kind="blocked", park_reason="agent stuck")
    _is(_read(facts), "waiting for her", "agent stuck")


def test_row_7_needs_you_without_a_reason() -> None:
    facts = _facts(None, status="needs_you", park_kind="blocked", park_reason=None)
    _is(_read(facts), "waiting for her")


def test_row_8_failed_run() -> None:
    _is(_read(_facts(status="failed")), "failed")


def test_row_9_cancelled_run_is_failed() -> None:
    _is(_read(_facts(status="cancelled")), "failed", "Run cancelled")


def test_row_10_build_run_done_waits_for_the_merge() -> None:
    _is(
        _read(_facts(status="done", initiative_position=1)),
        "running",
        "waiting for the pull request merge",
    )


def test_row_10_wins_over_a_later_done_run() -> None:
    build = _facts(status="done", initiative_position=1, minutes=0)
    later = _facts(status="done", initiative_position=2, minutes=5)
    _is(_read(later, build), "running", "waiting for the pull request merge")


def test_row_11_no_run() -> None:
    _is(_read(), "running", "next workflow starting")


def test_row_11_unconsumed_advance_without_reason() -> None:
    _is(_read(advances=(_advance(),)), "running", "next workflow starting")


def test_row_11_done_run_that_is_not_the_build_run() -> None:
    _is(_read(_facts(status="done", initiative_position=0)), "running", "next workflow starting")


def test_no_build_run_without_an_auto_entry_after_the_spec() -> None:
    sequence = a_sequence()
    spec = sequence.workflows[0]
    only_spec = sequence.model_copy(update={"workflows": (spec,)})
    _is(
        _read(_facts(status="done", initiative_position=1), sequence=only_spec),
        "running",
        "next workflow starting",
    )


def test_no_build_run_without_a_conversation_spec_entry() -> None:
    sequence = a_sequence()
    spec, build = sequence.workflows
    bare = spec.model_copy(update={"steps": ()})
    custom = sequence.model_copy(update={"workflows": (bare, build)})
    _is(
        _read(_facts(status="done", initiative_position=1), sequence=custom),
        "running",
        "next workflow starting",
    )


def test_latest_run_is_the_greatest_created_at_whatever_the_order() -> None:
    old = _facts(status="failed", minutes=0)
    new = _facts(status="queued", minutes=9)
    _is(_read(new, old), "running", "waiting for a slot")
    _is(_read(old, new), "running", "waiting for a slot")


def test_step_is_the_facts_step() -> None:
    assert _read(_facts(status="queued", step="ux")).step == "ux"


def test_step_falls_back_to_the_workflow_at_the_position() -> None:
    assert _read(_facts(status="queued", initiative_position=1)).step == "build"


def test_step_falls_back_to_the_first_workflow() -> None:
    assert _read(_facts(status="queued", initiative_position=None)).step == "spec"
    assert _read(_facts(status="queued", initiative_position=7)).step == "spec"
    assert _read().step == "spec"


def test_step_is_empty_with_no_workflow() -> None:
    empty = a_sequence().model_copy(update={"workflows": ()})
    assert _read(sequence=empty).step == ""


def test_frozen_workflow_type_is_used() -> None:
    assert isinstance(a_sequence().workflows[0], FrozenWorkflow)


def test_conversation_stop_without_attention_reads_as_any_other_stop() -> None:
    facts = _facts(None, status="needs_you", park_kind="conversation", park_reason="her turn")
    _is(_read(facts), "waiting for her", "her turn")
