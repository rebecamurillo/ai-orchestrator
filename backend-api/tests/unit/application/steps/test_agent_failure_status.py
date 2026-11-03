"""`AgentExecutor` over a failed attempt whose Story file says `in-progress` (story 1-2 review,
2026-11-02): exit 1, a 402 and a half-written file park under the provider's words, not under
`unexpected status`."""

from __future__ import annotations

from orchestrator.application.steps.agent import AgentExecutor
from tests.unit.application.steps.agent_tail_fixtures import a_story, contracted
from tests.unit.application.steps.test_agent_failure import OPENROUTER_402, failed_after_work


def test_exit_one_a_402_and_an_in_progress_file_name_the_provider_error() -> None:
    world = failed_after_work(
        raw={"is_error": True, "result": OPENROUTER_402},
        story=a_story("in-progress"),
        with_resolved=contracted(retry=None),
    )

    result = AgentExecutor().execute(world.ctx)

    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert (result.reason or "").startswith("provider error: API Error: 402")
    assert "unexpected status" not in (result.reason or "")


def test_an_in_progress_file_after_a_failure_that_is_not_the_providers_keeps_its_status() -> None:
    world = failed_after_work(
        raw={"is_error": True, "result": "API Error: connection reset"},
        story=a_story("in-progress"),
        with_resolved=contracted(retry=None),
    )

    result = AgentExecutor().execute(world.ctx)

    assert result.reason == "unexpected status: in-progress"
