"""`application/steps/pr_link.py`: the compare URL, or the honest absence of one (FR-11).

The two URL shapes a Repository is registered with, the `.git` suffix that is optional in
both, and every other host — which is `done`, because a Repository that is not on GitHub is
correctly configured and a Run that failed for it would be wrong.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, StepExecutor
from orchestrator.application.steps.pr_link import KIND, NO_LINK, PrLinkExecutor
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.step_fixtures import BRANCH, a_context, a_row, an_environment, without

COMPARE = "https://github.com/acme/widgets/compare/main...chore/bmad-init"


def a_link_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={"branch": BRANCH}, path="link")


def link(url: str, **overrides: object) -> object:
    context = a_context(a_link_row(), env=an_environment(repository_url=url, **overrides))
    return PrLinkExecutor().execute(context)


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(PrLinkExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), PrLinkExecutor)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/widgets.git",
        "https://github.com/acme/widgets",
        "https://github.com/acme/widgets/",
        "git@github.com:acme/widgets.git",
        "git@github.com:acme/widgets",
    ],
)
def test_every_shape_a_github_remote_is_written_in_yields_the_same_compare_url(
    url: str,
) -> None:
    result = link(url)

    assert result.status == "done"  # type: ignore[attr-defined]
    assert result.output_ref == COMPARE  # type: ignore[attr-defined]
    assert result.run_updates is not None  # type: ignore[attr-defined]
    assert result.run_updates.compare_urls == (COMPARE,)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "url",
    [
        "file:///work/e2e-fixtures/thing.git",
        "https://gitlab.com/acme/widgets.git",
        "https://mirror.example/github.com/acme/widgets",
    ],
)
def test_any_other_host_is_done_with_no_link_and_appends_nothing(url: str) -> None:
    result = link(url)

    assert result.status == "done"  # type: ignore[attr-defined]
    assert result.reason == NO_LINK  # type: ignore[attr-defined]
    assert result.run_updates is None  # type: ignore[attr-defined]


def test_a_second_epic_appends_its_own_link_beside_the_first() -> None:
    """`initiative@1` pushes one branch per epic and ends with one link per epic."""
    first = "https://github.com/acme/widgets/compare/main...feat/epic-1"
    result = link("https://github.com/acme/widgets.git", compare_urls=(first,))

    assert result.run_updates.compare_urls == (first, COMPARE)  # type: ignore[attr-defined]


def test_a_link_the_run_already_recorded_is_not_appended_twice() -> None:
    result = link("https://github.com/acme/widgets.git", compare_urls=(COMPARE,))

    assert result.run_updates.compare_urls == (COMPARE,)  # type: ignore[attr-defined]


def test_the_compare_url_names_the_repositorys_default_branch_as_the_base() -> None:
    result = link("https://github.com/acme/widgets.git", default_branch="trunk")

    assert result.output_ref == (  # type: ignore[attr-defined]
        "https://github.com/acme/widgets/compare/trunk...chore/bmad-init"
    )


def test_without_an_environment_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        PrLinkExecutor().execute(without(a_context(a_link_row()), run_env=None))
