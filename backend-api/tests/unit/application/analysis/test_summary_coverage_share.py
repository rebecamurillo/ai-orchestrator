"""The share row of coverage of changed lines (epic 6 story 1, AC2)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.summary import summarise
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.values import PARTIAL, MetricValue

COVERAGE = "code.coverage_changed_lines"


def signals(path: str, covered: int, instrumented: int) -> RepositorySignals:
    return RepositorySignals(
        path=path,
        status="ok",
        output="",
        counts=(
            Count(COVERAGE, "covered", covered, None),
            Count(COVERAGE, "instrumented", instrumented, None),
        ),
    )


def share(values: list[MetricValue], scope: str) -> MetricValue:
    return next(
        v
        for v in values
        if v.metric_id == COVERAGE and v.source == "share" and v.scope_type == scope
    )


def test_the_share_of_one_repository() -> None:
    values = summarise([signals(".", 30, 40)])
    row = share(values, "repository")
    assert (row.value_num, row.unit, row.method_id) == (Decimal("75.00"), "%", f"{COVERAGE}@1")
    assert share(values, "run").value_num == Decimal("75.00")
    covered = next(v for v in values if v.source == "covered")
    assert covered.unit == "lines"


def test_the_run_share_is_recomputed_from_the_summed_lines() -> None:
    values = summarise([signals("a", 1, 2), signals("b", 9, 10)])
    assert share(values, "run").value_num == Decimal("83.33")


def test_a_partial_run_keeps_the_partial_fields_on_its_share() -> None:
    other = RepositorySignals(path="b", status="ok", output="", counts=())
    row = share(summarise([signals("a", 3, 4), other]), "run")
    assert (row.missing, row.partial_n, row.partial_m) == (PARTIAL, 1, 2)


def test_no_instrumented_line_is_a_word() -> None:
    row = share(summarise([signals(".", 0, 0)]), "repository")
    assert row.value_num is None
    assert row.missing == "n/a — no added production line instrumented"


def test_a_word_for_either_figure_gives_no_share() -> None:
    words = RepositorySignals(
        path=".",
        status="ok",
        output="",
        counts=(),
        words={COVERAGE: "n/a — no coverage command declared"},
    )
    assert [v for v in summarise([words]) if v.source == "share"] == []
    only_covered = RepositorySignals(
        path=".", status="ok", output="", counts=(Count(COVERAGE, "covered", 1, None),)
    )
    assert [v for v in summarise([only_covered]) if v.source == "share"] == []
