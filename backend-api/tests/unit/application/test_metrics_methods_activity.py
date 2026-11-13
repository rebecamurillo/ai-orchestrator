"""Activity methods over small inputs (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.methods import REGISTRY, activity
from orchestrator.application.metrics.values import value_at
from orchestrator.domain.entities.facts import ActivityFact, AttemptFacts, GapFact
from tests.unit.application.metrics_builders import at, make_ai, make_attempt, make_inputs, make_row


def gap(conversation: str, messages: int, *gaps: int) -> GapFact:
    return GapFact(
        conversation=conversation, messages=messages, first_at=at(0), last_at=at(9), gaps_s=gaps
    )


def tool(name: str, calls: int, errors: int = 0) -> ActivityFact:
    return ActivityFact(
        conversation="main",
        tool=name,
        calls=calls,
        errors=errors,
        files_read=calls,
        files_edited=1,
        test_runs=2,
        messages=0,
    )


def facts_inputs(facts: AttemptFacts | None):  # type: ignore[no-untyped-def]
    row = make_row()
    return make_inputs([row], [make_ai(row, facts=facts)])


def test_messages_split_session_and_subagents() -> None:
    inputs = facts_inputs(AttemptFacts(gaps=(gap("main", 10), gap("sub-1", 4), gap("sub-2", 6))))
    assert value_at(
        activity.messages_session(inputs), "activity.messages_session", "run", "run"
    ).value_num == Decimal(10)
    assert value_at(
        activity.messages_subagents(inputs), "activity.messages_subagents", "run", "run"
    ).value_num == Decimal(10)


def test_no_conversation_of_the_kind_reads_not_available() -> None:
    inputs = facts_inputs(AttemptFacts(gaps=(gap("main", 10),)))
    assert (
        value_at(
            activity.messages_subagents(inputs), "activity.messages_subagents", "run", "run"
        ).missing
        == "not available"
    )


def test_no_facts_read_not_recorded() -> None:
    inputs = facts_inputs(None)
    assert (
        value_at(
            activity.messages_session(inputs), "activity.messages_session", "run", "run"
        ).missing
        == "not recorded"
    )
    longest = activity.pause_longest(inputs)
    assert {v.missing for v in longest} == {"not recorded"}


def test_pauses_over_the_cache_lifetime_use_the_conversation_lifetime() -> None:
    inputs = facts_inputs(
        AttemptFacts(gaps=(gap("main", 3, 3600, 3601), gap("sub", 3, 300, 301, 5000)))
    )
    found = activity.pauses_over_cache_lifetime(inputs)
    assert value_at(
        found, "activity.pauses_over_cache_lifetime", "run", "run"
    ).value_num == Decimal(3)
    bare = facts_inputs(AttemptFacts())
    assert (
        value_at(
            activity.pauses_over_cache_lifetime(bare),
            "activity.pauses_over_cache_lifetime",
            "run",
            "run",
        ).missing
        == "not available"
    )


def test_the_longest_pause_is_a_maximum_per_attempt_conversation_and_run() -> None:
    inputs = facts_inputs(AttemptFacts(gaps=(gap("main", 3, 30, 90), gap("sub", 3, 600))))
    values = activity.pause_longest(inputs)
    assert value_at(values, "activity.pause_longest", "run", "run").value_num == Decimal(600)
    assert value_at(values, "activity.pause_longest", "conversation", "main").value_num == Decimal(
        90
    )
    assert value_at(values, "activity.pause_longest", "conversation", "sub").value_num == Decimal(
        600
    )


def test_a_conversation_with_only_short_gaps_has_a_pause_of_zero_seconds() -> None:
    values = activity.pause_longest(facts_inputs(AttemptFacts(gaps=(gap("main", 3, 5),))))
    assert value_at(values, "activity.pause_longest", "run", "run").value_num == Decimal(0)


def test_pause_longest_takes_the_maximum_across_attempts() -> None:
    row = make_row()
    low = make_ai(row, facts=AttemptFacts(gaps=(gap("main", 2, 70),)))
    high = make_ai(row, make_attempt(row, 2), facts=AttemptFacts(gaps=(gap("main", 2, 700),)))
    low_again = make_ai(row, make_attempt(row, 3), facts=AttemptFacts(gaps=(gap("main", 2, 80),)))
    values = activity.pause_longest(make_inputs([row], [low, high, low_again]))
    assert value_at(values, "activity.pause_longest", "run", "run").value_num == Decimal(700)


def test_pause_longest_mixes_a_missing_attempt_with_a_found_one() -> None:
    row = make_row()
    found = make_ai(row, facts=AttemptFacts(gaps=(gap("main", 2, 70),)))
    bare = make_ai(row, make_attempt(row, 2), facts=AttemptFacts())
    run = value_at(
        activity.pause_longest(make_inputs([row], [bare, found])),
        "activity.pause_longest",
        "run",
        "run",
    )
    assert (run.value_num, run.missing) == (Decimal(70), "partial")


def test_tool_calls_errors_files_and_test_runs() -> None:
    inputs = facts_inputs(AttemptFacts(activity=(tool("Bash", 4, 1), tool("Read", 6, 0))))
    calls = activity.tool_calls(inputs)
    assert value_at(calls, "activity.tool_calls", "run", "run").value_num == Decimal(10)
    assert value_at(calls, "activity.tool_calls", "tool", "Bash").value_num == Decimal(4)
    errors = activity.tool_errors(inputs)
    assert value_at(errors, "activity.tool_errors", "run", "run").value_num == Decimal(1)
    assert value_at(
        REGISTRY["activity.files_read@1"](inputs), "activity.files_read", "run", "run"
    ).value_num == Decimal(10)
    assert value_at(
        REGISTRY["activity.files_edited@1"](inputs), "activity.files_edited", "run", "run"
    ).value_num == Decimal(2)
    assert value_at(
        REGISTRY["activity.test_runs@1"](inputs), "activity.test_runs", "run", "run"
    ).value_num == Decimal(4)


def test_an_attempt_without_activity_rows_reads_not_available_and_without_facts_not_recorded() -> (
    None
):
    assert (
        value_at(
            activity.tool_calls(facts_inputs(AttemptFacts())), "activity.tool_calls", "run", "run"
        ).missing
        == "not available"
    )
    none = activity.tool_calls(facts_inputs(None))
    assert value_at(none, "activity.tool_calls", "run", "run").missing == "not recorded"
    assert not [v for v in none if v.scope_type == "tool"]
