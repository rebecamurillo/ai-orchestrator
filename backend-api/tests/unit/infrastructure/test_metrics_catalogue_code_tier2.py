"""The five Tier 2 catalogue entries (epic 6 story 1, AC10)."""

from __future__ import annotations

from orchestrator.application.analysis import tier2, tier2_reports
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue


def entry(metric_id: str):  # type: ignore[no-untyped-def]
    return next(e for e in PackageCatalogue().entries() if e.id == metric_id)


def test_each_entry_is_level_a_with_the_missing_words() -> None:
    for metric_id in tier2.TIER2_IDS:
        found = entry(metric_id)
        assert found.level == "A"
        assert tuple(found.missing_words) == ("n/a", "not run", "partial")
        assert [m.n for m in found.methods] == [1]


def test_the_parameters_equal_the_module_constants() -> None:
    patterns = list(entry(tier2.LINT).methods[0].parameters["line_patterns"])
    assert patterns == [tier2_reports.LINE_PATTERN, tier2_reports.TSC_PATTERN]
    assert entry(tier2.TYPECHECK).methods[0].parameters["line_patterns"] == patterns
    fail = entry(tier2.FAIL_TO_PASS).methods[0].parameters
    assert fail["import_error_pattern"] == tier2_reports.IMPORT_ERROR_PATTERN
    for metric_id in tier2.TIER2_IDS:
        parameters = entry(metric_id).methods[0].parameters
        assert parameters["output_tail_chars"] == tier2.OUTPUT_TAIL_CHARS
        assert parameters["timeout_setting"] == "ANALYSIS_COMMAND_TIMEOUT_MIN"
