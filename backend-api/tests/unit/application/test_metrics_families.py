"""Role families: sums within one scope type, `orchestrate` only inside a story frame (AC4)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.metrics.families import (
    FAMILIES,
    family_applies,
    family_results,
    orchestrate_in_story,
)
from orchestrator.application.metrics.values import NO_SUCH_STEP
from tests.unit.application.metrics_builders import make_row
from tests.unit.application.test_metric_versions import stored
from tests.unit.fakes.catalogue import catalogue_entry

A, B = UUID(int=1), UUID(int=2)
STORY = "epics[0].stories[0]"


def role(name: str, figure: int | None, metric: str = "cost.gateway", **over: object):
    fields: dict[str, object] = {
        "scope_type": "role",
        "scope_key": name,
        "role": name,
        "value_num": None if figure is None else Decimal(figure),
        **over,
    }
    return stored(metric, **fields)


def attempt(path: str, figure: int, n: int = 1):
    return stored(
        "cost.gateway",
        scope_type="attempt",
        scope_key=f"{path}#{n}",
        role="orchestrate",
        value_num=Decimal(figure),
    )


def rows_of(*paths: str):
    return [make_row(path, seq=n, role="orchestrate") for n, path in enumerate(paths, start=1)]


def test_the_families_are_the_declared_seven_and_never_group_as_declared_roles() -> None:
    assert FAMILIES[0][0] == "story work"
    assert len(FAMILIES) == 7  # noqa: PLR2004
    assert all(not r.startswith("as declared") for _, roles in FAMILIES for r in roles)


def test_a_family_applies_to_role_scoped_additive_metrics_only() -> None:
    assert family_applies(catalogue_entry(scopes=("run", "role"), additive="within_scope_type"))
    assert family_applies(catalogue_entry(scopes=("role",), additive=True))
    assert not family_applies(catalogue_entry(scopes=("role",), additive=False))
    assert not family_applies(catalogue_entry(scopes=("run",), additive=True))


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ([], "none"),
        ([f"{STORY}.orchestrate"], "all"),
        (["orchestrate"], "none"),
        (["orchestrate", f"{STORY}.orchestrate"], "mixed"),
    ],
)
def test_orchestrate_in_story_reads_the_step_rows(paths: list[str], expected: str) -> None:
    assert orchestrate_in_story(rows_of(*paths)) == expected


def test_orchestrate_rows_of_other_roles_are_not_counted() -> None:
    assert orchestrate_in_story([make_row("plan", role="plan")]) == "none"


def test_story_work_sums_each_runs_roles_and_flags_a_different_structure() -> None:
    values = {
        A: [role("plan", 3), role("implement", 4), role("review", 2)],
        B: [role("orchestrate", 7)],
    }

    [story] = family_results(values, {A: "none", B: "all"})

    assert story.family == "story work"
    assert story.step_structure_differs is True
    assert (story.cells[A].value_num, story.cells[A].roles) == (
        Decimal(9),
        ("plan", "implement", "review"),
    )
    assert (story.cells[B].value_num, story.cells[B].roles) == (Decimal(7), ("orchestrate",))


def test_equal_role_sets_do_not_differ() -> None:
    values = {A: [role("plan", 1)], B: [role("plan", 5)]}

    [story] = family_results(values, {A: "none", B: "none"})

    assert story.step_structure_differs is False


def test_orchestrate_outside_a_story_frame_contributes_nothing() -> None:
    values = {A: [role("plan", 3)], B: [role("orchestrate", 7)]}

    [story] = family_results(values, {A: "none", B: "none"})

    assert story.cells[B].value_num is None
    assert story.cells[B].missing == NO_SUCH_STEP
    assert story.cells[B].roles == ()
    assert story.step_structure_differs is False


def test_mixed_orchestrate_sums_only_the_attempts_inside_a_story_frame() -> None:
    values = {
        A: [role("plan", 3)],
        B: [
            role("orchestrate", 99),
            attempt(f"{STORY}.orchestrate", 5),
            attempt(f"{STORY}.orchestrate", 2, n=2),
            attempt("orchestrate", 40),
        ],
    }

    [story] = family_results(values, {A: "none", B: "mixed"})

    assert story.cells[B].value_num == Decimal(7)


def test_mixed_orchestrate_without_attempt_rows_contributes_nothing() -> None:
    values = {A: [role("plan", 3)], B: [role("orchestrate", 99)]}

    [story] = family_results(values, {A: "none", B: "mixed"})

    assert story.cells[B].missing == NO_SUCH_STEP


def test_a_missing_figure_makes_the_family_partial_and_never_zero() -> None:
    values = {
        A: [role("plan", 3), role("implement", None, missing="not recorded")],
        B: [role("plan", 1)],
    }

    [story] = family_results(values, {A: "none", B: "none"})

    assert (story.cells[A].value_num, story.cells[A].missing) == (Decimal(3), "partial")
    assert story.cells[B].missing is None


def test_a_partial_contribution_keeps_the_family_partial() -> None:
    values = {A: [role("plan", 3, missing="partial")], B: [role("plan", 1)]}

    [story] = family_results(values, {A: "none", B: "none"})

    assert (story.cells[A].value_num, story.cells[A].missing) == (Decimal(3), "partial")


def test_with_no_figure_anywhere_the_word_shows() -> None:
    values = {A: [role("plan", None, missing="not recorded")], B: [role("plan", 1)]}

    [story] = family_results(values, {A: "none", B: "none"})

    assert (story.cells[A].value_num, story.cells[A].missing) == (None, "not recorded")


def test_a_contributor_with_several_rows_folds_them_and_sources_stay_apart() -> None:
    values = {
        A: [
            role("plan", 1, source="harness"),
            role("plan", 2, source="harness"),
            role("plan", 9, source="gateway"),
        ],
        B: [role("plan", 4, source="harness")],
    }

    gateway, harness = family_results(values, {A: "none", B: "none"})

    assert gateway.source == "gateway" and harness.source == "harness"
    assert harness.cells[A].value_num == Decimal(3)
    assert gateway.cells[A].value_num == Decimal(9)
    assert gateway.cells[B].missing == NO_SUCH_STEP


def test_other_scope_types_never_enter_a_role_sum() -> None:
    values = {
        A: [stored("cost.gateway", scope_type="run", scope_key="run", value_num=Decimal(50))],
        B: [],
    }

    assert family_results(values, {A: "none", B: "none"}) == []


def test_each_family_is_reported_in_declared_order() -> None:
    values = {A: [role("verify", 1), role("plan", 1), role("senior", 1)], B: [role("chat", 1)]}

    names = [r.family for r in family_results(values, {A: "none", B: "none"})]

    assert names == ["story work", "verification", "senior", "chat"]
