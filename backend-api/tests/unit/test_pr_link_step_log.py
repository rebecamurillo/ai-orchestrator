"""`pr.link` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.pr_link import KIND, NO_LINK, PrLinkExecutor
from tests.unit.step_fixtures import (
    BRANCH,
    REPOSITORY_URL,
    a_context,
    a_row,
    an_environment,
    without,
)


def a_link_context(url: str) -> StepContext:
    row = a_row(kind=KIND, with_resolved={"branch": BRANCH}, path="link")
    return a_context(row, env=an_environment(repository_url=url))


def test_a_github_link_logs_its_header_and_the_url() -> None:
    ctx = a_link_context(REPOSITORY_URL)

    result = PrLinkExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    writes = ctx.ports.step_log.writes  # type: ignore[union-attr]
    assert len(writes) == 1
    assert writes[0][3] == (f"> compare link from {REPOSITORY_URL}", f"  {result.output_ref}")


def test_another_host_logs_that_there_is_no_link() -> None:
    ctx = a_link_context("file:///srv/repo.git")

    result = PrLinkExecutor().execute(ctx)

    assert result.reason == NO_LINK
    assert result.log_path == str(log_path(ctx))
    assert ctx.ports.step_log.writes[0][3] == (  # type: ignore[union-attr]
        "> compare link from file:///srv/repo.git",
        f"  {NO_LINK}",
    )


def test_without_a_step_log_the_result_is_the_same_minus_the_path() -> None:
    for url in (REPOSITORY_URL, "file:///srv/repo.git"):
        result = PrLinkExecutor().execute(a_link_context(url))
        plain = PrLinkExecutor().execute(without(a_link_context(url), step_log=None))

        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
