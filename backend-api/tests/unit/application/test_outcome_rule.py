"""`application/rules/outcome.py` (O-6 of _bmad-output/specs/unattended-hub-run/PLAN.md):
the phrase a `protected_path` park appends for the route it is hiding."""

from __future__ import annotations

from orchestrator.application.rules.outcome import routed_outcome
from orchestrator.domain.values import Park, Retry, StepResult


def _stop(kind: str, reason: str) -> StepResult:
    return StepResult(
        status="error",
        gate="liveness",
        reason=reason,
        park=Park(kind=kind, reason=reason, path="p"),  # type: ignore[arg-type]
    )


def test_a_plain_done_is_story_done() -> None:
    assert routed_outcome(StepResult(status="done", gate="liveness"), None) == "story done"


def test_a_blocked_story_names_its_condition() -> None:
    assert (
        routed_outcome(_stop("blocked", "## section"), "intent gap") == "story blocked: intent gap"
    )


def test_a_blocked_story_without_a_condition_names_its_section() -> None:
    assert routed_outcome(_stop("blocked", "## section"), None) == "story blocked: ## section"


def test_a_retry_or_another_stop_is_its_own_reason() -> None:
    retry = StepResult(
        status="error",
        gate="liveness",
        reason="unexpected status: in-review",
        retry=Retry(prompt="x", max=1, resume_session=True),
    )

    assert routed_outcome(retry, None) == "unexpected status: in-review"
    assert routed_outcome(_stop("misconfigured", "no story file"), None) == "no story file"


def test_a_stop_without_a_reason_falls_back_to_done() -> None:
    bare = StepResult(
        status="error", gate="liveness", park=Park(kind="budget", reason="", path="p")
    )

    assert routed_outcome(bare, None) == "story done"
