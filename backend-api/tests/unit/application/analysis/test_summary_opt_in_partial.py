"""Tier 2 run rows say `partial` when only some repositories opted in (epic 6 story 4, AC1)."""

from __future__ import annotations

from orchestrator.application.analysis.findings import FINDINGS_IDS, NO_RULES
from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.summary import OPT_IN_METRICS, summarise
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.tier2 import NOT_DECLARED, TIER2_IDS
from orchestrator.application.metrics.values import PARTIAL, MetricValue

LINT = "code.linter_warnings_new"
COVERAGE = "code.coverage_changed_lines"
SECURITY = "code.findings_security"
THREE = 3


def opted(path: str = "repos/app") -> RepositorySignals:
    return RepositorySignals(
        path=path,
        status="ok",
        output="",
        counts=(
            Count(LINT, None, THREE, None),
            Count(COVERAGE, "covered", 30, None),
            Count(COVERAGE, "instrumented", 40, None),
            Count(SECURITY, "high", THREE, None),
        ),
    )


def not_opted(path: str = ".") -> RepositorySignals:
    words = {
        **dict.fromkeys(TIER2_IDS, NOT_DECLARED),
        **dict.fromkeys(FINDINGS_IDS, NO_RULES),
    }
    return RepositorySignals(path=path, status="ok", output="", counts=(), words=words)


def run_rows(values: list[MetricValue], metric_id: str) -> list[MetricValue]:
    return [v for v in values if v.scope_type == "run" and v.metric_id == metric_id]


def test_the_opt_in_ids_are_the_tier_2_and_findings_ids() -> None:
    assert set(OPT_IN_METRICS) == {*TIER2_IDS, *FINDINGS_IDS}


def test_one_repository_of_two_makes_every_figure_partial_and_drops_the_word() -> None:
    values = summarise([not_opted("."), opted()])

    for metric_id in (LINT, COVERAGE, SECURITY):
        rows = run_rows(values, metric_id)
        assert rows
        assert all(r.value_num is not None for r in rows)
        assert all((r.missing, r.partial_n, r.partial_m) == (PARTIAL, 1, 2) for r in rows)
    repo = [v for v in values if v.scope_type == "repository" and v.repository == "."]
    assert {v.missing for v in repo if v.metric_id == LINT} == {NOT_DECLARED}


def test_a_metric_no_repository_measured_keeps_its_word() -> None:
    values = summarise([not_opted("."), not_opted("repos/app")])

    [row] = run_rows(values, LINT)
    assert (row.value_num, row.missing) == (None, NOT_DECLARED)


def test_a_failed_repository_is_not_a_figure_and_the_other_stays_partial() -> None:
    failed = RepositorySignals(path=".", status="failed", output="boom\nmore", counts=())

    [row] = run_rows(summarise([failed, opted()]), LINT)

    assert (row.value_num, row.missing, row.partial_n, row.partial_m) == (THREE, PARTIAL, 1, 2)


def test_a_tier_1_word_beside_sourced_rows_is_unchanged() -> None:
    plain = RepositorySignals(
        path=".", status="ok", output="", counts=(), words={"code.lines_added": "n/a — x"}
    )
    other = RepositorySignals(
        path="b", status="ok", output="", counts=(Count("code.lines_added", "production", 5, None),)
    )

    rows = run_rows(summarise([plain, other]), "code.lines_added")

    assert [r.value_num for r in rows if r.source == "production"] == [5]
    assert any(r.value_num is None and r.source is None for r in rows)
