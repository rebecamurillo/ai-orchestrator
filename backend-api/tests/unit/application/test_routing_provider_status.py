"""`rules/routing.py::route`: a failed exit names the provider's reason for an unexpected status
too (story 1-2 review, Operator decision 2026-11-02). Before it, an agent that died on a 402
mid-story read `unexpected status: in-progress` and sent the Operator to the Story file."""

from __future__ import annotations

from orchestrator.application.rules.routing import (
    UNEXPECTED_STATUS,
    RouteContract,
    route,
)
from orchestrator.application.story_file import StoryFile
from orchestrator.domain.values import Retry, StepResult

PROVIDER = "provider error: API Error: 402 Insufficient credits"
CONTRACT = RouteContract(success=("done",), blocked=("blocked",), checkpoint=("ready-for-dev",))


def reached(
    status: str, exit_code: int | None, exit_reason: str | None, retry: Retry | None = None
) -> StepResult:
    story = StoryFile(path="s/4-1-x.md", status=status, auto_run_result="", blocking_condition=None)
    return route(
        story,
        [story.path],
        exit_code,
        False,
        0,
        retry,
        contract=CONTRACT,
        gate="liveness",
        path="build",
        exit_reason=exit_reason,
    )


def test_an_in_progress_file_after_a_failed_exit_names_the_provider_error() -> None:
    result = reached("in-progress", 1, PROVIDER)

    assert result.reason == PROVIDER
    assert result.park is not None
    assert (result.park.kind, result.park.reason) == ("misconfigured", PROVIDER)


def test_the_provider_reason_takes_the_declared_retry_here_too() -> None:
    retry = Retry(prompt="again", max=1)

    result = reached("in-progress", 1, PROVIDER, retry)

    assert result.reason == PROVIDER
    assert result.park is None
    assert result.retry == retry


def test_without_a_provider_reason_the_status_is_named_as_before() -> None:
    expected = UNEXPECTED_STATUS.format(status="in-progress")

    assert reached("in-progress", 1, None).reason == expected
    assert reached("in-progress", 0, None).reason == expected


def test_a_reason_beside_a_clean_exit_does_not_replace_the_status() -> None:
    expected = UNEXPECTED_STATUS.format(status="in-progress")

    assert reached("in-progress", 0, PROVIDER).reason == expected
    assert reached("in-progress", None, PROVIDER).reason == expected
