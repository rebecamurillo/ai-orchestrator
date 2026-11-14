"""Toolset fingerprints and the sized diff of a comparison (epic 5 story 5, AC6-AC8)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.analysis.toolset import toolset_records, with_toolset
from orchestrator.application.metrics.compare_toolsets import (
    DECLARATION_TOOL,
    diff_size_words,
    fingerprints_differ,
    run_toolset,
)
from orchestrator.application.metrics.compare_views import ToolVersion
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ids import new_id
from tests.unit.application.test_metric_versions import stored


def _analysis(jscpd: str, declaration: str | None = "abcdef123456") -> Analysis:
    base = Analysis(
        id=new_id(),
        run_id=new_id(),
        repository_path=".",
        status="ok",
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    records = toolset_records(
        {"gitleaks": "8.0", "jscpd": jscpd, "lizard": "1.0", "osv-scanner": "2.0"},
        vulnerability_db_date=None,
        lookup_date=None,
        declaration_hash=declaration,
    )
    return with_toolset(base, records)


def test_run_toolset_joins_distinct_versions_and_adds_the_declaration() -> None:
    toolset = run_toolset([_analysis("4.0.5"), _analysis("4.1.0")])

    assert ToolVersion("jscpd", "4.0.5/4.1.0") in toolset
    assert ToolVersion("gitleaks", "8.0") in toolset
    assert toolset[-1] == ToolVersion(DECLARATION_TOOL, "abcdef12")
    assert [t.tool for t in toolset[:-1]] == sorted(t.tool for t in toolset[:-1])


def test_run_toolset_names_an_absent_declaration() -> None:
    assert run_toolset([_analysis("4.0.5", None)])[-1] == ToolVersion(DECLARATION_TOOL, "absent")


def test_fingerprints_differ_ignores_none() -> None:
    assert fingerprints_differ(["a", None, "b"]) is True
    assert fingerprints_differ(["a", None, "a"]) is False
    assert fingerprints_differ([]) is False


def _row(metric: str, figure: str | None, source: str | None = None, **over: object):  # type: ignore[no-untyped-def]
    return stored(
        metric,
        scope_type="run",
        scope_key="run",
        source=source,
        value_num=None if figure is None else Decimal(figure),
        **over,
    )


def test_diff_size_words_sums_raw_run_scope_rows_only() -> None:
    values = [
        _row("code.lines_added", "30", "production"),
        _row("code.lines_added", "12", "test"),
        _row("code.lines_added", "1.5", "production:per_100"),
        _row("code.lines_added", "9", "small_change"),
        _row("code.lines_removed", "5"),
        _row("code.files_touched", "7"),
        stored("code.files_touched", scope_type="repository", scope_key=".", value_num=Decimal(99)),
    ]

    assert diff_size_words(values, True) == "+42 \N{MINUS SIGN}5 · 7 files"


def test_diff_size_words_not_analysed_and_missing() -> None:
    assert diff_size_words([], False) == "not run"
    assert diff_size_words([], True) == "not run"
    word = _row("code.lines_added", None, missing="not run — no analysis")
    assert diff_size_words([word], True) == "not run — no analysis"
