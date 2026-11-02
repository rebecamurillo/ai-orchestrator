"""The senior's `verify_failed` diagnosis in a fresh dispatch (story 1-6, spine AD-10/AD-22,
2026-11-02).

It is told in a new session, beside the failure the redispatch clause quotes, and never into
the row's old one. A row that declares no `redispatch` clause is still told the diagnosis."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.steps.agent_prompt import redispatch_clause
from orchestrator.application.steps.verify_failure import VerifyFailure
from tests.unit.application.steps.agent_fixtures import resolved
from tests.unit.application.steps.agent_tail_fixtures import a_tail_world
from tests.unit.application.steps.test_agent_retry_dispatch import (
    DISPATCH,
    REDISPATCH_CLAUSE_FILLED,
    VERIFY_FAILURE,
    a_previous,
    failing_verify,
    run,
    with_redispatch_clause,
)

DIAGNOSIS = "Senior reviewer's diagnosis: the mock is stale; regenerate it."
DIAGNOSED = replace(VERIFY_FAILURE, diagnosis=DIAGNOSIS)


def test_the_clause_is_followed_by_the_diagnosis_in_a_new_session() -> None:
    world = a_tail_world(previous=a_previous("done"), with_resolved=with_redispatch_clause())

    run(failing_verify(world, DIAGNOSED))

    assert world.harness.called("resume") == []
    [started] = world.harness.called("start")
    assert started["prompt"] == f"{REDISPATCH_CLAUSE_FILLED} {DIAGNOSIS} {DISPATCH}"


def test_a_row_with_no_redispatch_clause_is_still_told_the_diagnosis() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world, DIAGNOSED))

    assert world.harness.called("start")[0]["prompt"] == f"{DIAGNOSIS} {DISPATCH}"


def test_a_diagnosis_owed_after_a_crash_is_told_with_the_failure_again() -> None:
    """The interrupted attempt never came back (`end_sha` unset), so this new session has
    heard neither the failure nor the diagnosis."""
    previous = a_previous("error", end_sha=None)
    world = a_tail_world(previous=previous, with_resolved=with_redispatch_clause())

    run(failing_verify(world, DIAGNOSED))

    prompt = world.harness.called("start")[0]["prompt"]
    assert prompt == f"{REDISPATCH_CLAUSE_FILLED} {DIAGNOSIS} {DISPATCH}"


def test_a_failure_nobody_diagnosed_changes_nothing() -> None:
    world = a_tail_world(previous=a_previous("done"), with_resolved=with_redispatch_clause())

    run(failing_verify(world))

    assert world.harness.called("start")[0]["prompt"] == f"{REDISPATCH_CLAUSE_FILLED} {DISPATCH}"


def test_a_dispatch_with_no_environment_facts_sends_the_plain_prompt() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world, None))

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


# ── the clause ───────────────────────────────────────────────────────────────


def test_redispatch_clause_appends_the_diagnosis_to_the_filled_clause() -> None:
    with_resolved = resolved(prompts={"redispatch": "Failed: {command} (exit {code})."})
    failure = VerifyFailure(command="make test", exit_code=2, diagnosis="Regenerate it.")

    assert redispatch_clause(with_resolved, failure) == "Failed: make test (exit 2). Regenerate it."


def test_redispatch_clause_with_no_clause_is_the_diagnosis_alone() -> None:
    failure = VerifyFailure(command="make test", exit_code=2, diagnosis="Regenerate it.")

    assert redispatch_clause(resolved(prompts={}), failure) == "Regenerate it."


def test_diagnosis_text_is_never_scanned_for_tokens() -> None:
    with_resolved = resolved(prompts={"redispatch": "{tail}"})
    failure = VerifyFailure(command="c", exit_code=1, log_tail=("x",), diagnosis="see {command}")

    assert redispatch_clause(with_resolved, failure) == "x see {command}"
