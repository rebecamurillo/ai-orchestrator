"""`rules/routing.py::route` takes the reason a failed attempt gives in place of
`harness exit {code}` (SPEC senior-unblock CAP-5, story 1-2, 2026-11-02). Only the two
sentences that name the exit code change; every other branch of the FR-16 table is as it was."""

from __future__ import annotations

from orchestrator.application.rules.routing import HARNESS_EXIT, RouteContract, route
from orchestrator.application.story_file import StoryFile
from orchestrator.domain.values import Retry, StepResult

PROVIDER = "provider error: API Error: 402 Insufficient credits"
CONTRACT = RouteContract(success=("done",), blocked=("blocked",), checkpoint=("ready-for-dev",))
PATH = "build"
STORY = "s/4-1-x.md"


def done_file() -> StoryFile:
    return StoryFile(path=STORY, status="done", auto_run_result="", blocking_condition=None)


def reached(
    *,
    story: StoryFile | None = None,
    exit_code: int | None = 1,
    exit_reason: str | None = None,
    retry: Retry | None = None,
    retry_count: int = 0,
) -> StepResult:
    return route(
        story,
        [STORY] if story is not None else [],
        exit_code,
        False,
        retry_count,
        retry,
        contract=CONTRACT,
        gate="liveness",
        path=PATH,
        exit_reason=exit_reason,
    )


def test_an_empty_glob_after_a_failed_exit_reads_the_provider_reason() -> None:
    result = reached(exit_reason=PROVIDER)

    assert result.reason == PROVIDER
    assert result.park is not None
    assert (result.park.kind, result.park.reason, result.park.path) == (
        "misconfigured",
        PROVIDER,
        PATH,
    )


def test_a_done_file_overruled_by_a_failed_exit_reads_the_provider_reason() -> None:
    result = reached(story=done_file(), exit_reason=PROVIDER)

    assert result.reason == PROVIDER
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_without_a_reason_the_exit_code_is_named_as_before() -> None:
    assert reached().reason == HARNESS_EXIT.format(code=1)
    assert reached(story=done_file()).reason == HARNESS_EXIT.format(code=1)


def test_a_reason_changes_nothing_when_the_exit_was_clean() -> None:
    clean = reached(story=done_file(), exit_code=0, exit_reason=PROVIDER)

    assert clean.status == "done"
    assert reached(exit_code=0, exit_reason=PROVIDER).reason == "no story file"


def test_a_failed_exit_beside_a_done_file_takes_the_rows_declared_retry_and_no_other() -> None:
    retry = Retry(prompt="again", max=1)

    first = reached(story=done_file(), exit_reason=PROVIDER, retry=retry, retry_count=0)
    spent = reached(story=done_file(), exit_reason=PROVIDER, retry=retry, retry_count=1)

    assert first.status == "error"
    assert first.park is None
    assert first.retry == retry
    assert first.reason == PROVIDER
    assert spent.park is not None
    assert spent.park.kind == "misconfigured"
    assert spent.park.reason == PROVIDER
