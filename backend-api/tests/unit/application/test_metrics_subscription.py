"""The subscription rule of a Run and of a project's Runs (epic 4 story 1, AC10)."""

from __future__ import annotations

import pytest

from orchestrator.application.metrics.subscription import group_subscription, run_subscription


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([True, None], True),
        ([True], True),
        ([False, True, None], True),
        ([False, False], False),
        ([False], False),
        ([False, None], None),
        ([None], None),
        ([], None),
    ],
)
def test_a_runs_subscription_over_its_fact_sets(
    flags: list[bool | None], expected: bool | None
) -> None:
    assert run_subscription(flags) is expected


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([True, None], True),
        ([False, False], False),
        ([False, None], None),
        ([], None),
    ],
)
def test_a_projects_flag_follows_the_same_rule_over_its_runs(
    flags: list[bool | None], expected: bool | None
) -> None:
    assert group_subscription(flags) is expected
