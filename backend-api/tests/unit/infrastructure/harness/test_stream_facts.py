"""The shared reading of an event stream's framing (stream_facts)."""

from __future__ import annotations

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.stream_facts import (
    NO_CAPABILITIES,
    split_events,
    status_and_reason,
    usage_row,
)


def test_unknown_types_are_sorted_and_distinct_and_untyped_objects_are_ignored() -> None:
    objects = [
        {"type": "known"},
        {"type": "foo"},
        {"type": "bar"},
        {"type": "foo"},
        {"severity": "error"},
        {"type": 3},
    ]

    events, unknown = split_events(objects, frozenset({"known"}))

    assert events == [{"type": "known"}, {"type": "foo"}, {"type": "bar"}, {"type": "foo"}]
    assert unknown == ("bar", "foo")


def test_status_and_reason_cover_the_four_combinations() -> None:
    assert status_and_reason(True, ()) == ("ok", None)
    assert status_and_reason(False, ()) == ("partial", "no usage event")
    assert status_and_reason(True, ("foo",)) == ("partial", "unknown event types: foo")
    assert status_and_reason(False, ("bar", "foo")) == (
        "partial",
        "no usage event; unknown event types: bar, foo",
    )


def test_a_usage_row_is_a_harness_row_for_the_attempts_model() -> None:
    attempt = Attempt(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done", model="m"
    )

    row = usage_row(attempt, "output", 5)

    assert (row.source, row.model, row.conversation) == ("harness", "m", "main")
    assert (row.usage_class, row.tokens, row.usd, row.subagent_type) == ("output", 5, None, None)


def test_no_capabilities_are_all_false() -> None:
    assert not any(vars(NO_CAPABILITIES).values())
