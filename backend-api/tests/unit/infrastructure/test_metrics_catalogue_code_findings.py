"""The two Opengrep finding entries of `code.yaml` (epic 6 story 2, AC8)."""

from __future__ import annotations

from orchestrator.application.analysis import findings, findings_sarif
from orchestrator.application.analysis.summary import OPEN_SOURCE_METRICS
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue


def entry(metric_id: str):  # type: ignore[no-untyped-def]
    return next(e for e in PackageCatalogue().entries() if e.id == metric_id)


def test_labels_levels_and_missing_words() -> None:
    security, bug = entry(findings.SECURITY), entry(findings.BUG)
    assert (security.label, security.level) == (
        "possible security findings, new, by severity (CWE)",
        "H",
    )
    assert (bug.label, bug.level) == ("possible bug findings, new", "A")
    for found in (security, bug):
        assert tuple(found.missing_words) == ("n/a", "not run", "partial")
        assert [m.n for m in found.methods] == [1]
        assert found.id not in OPEN_SOURCE_METRICS
        assert found.group == "code"
        assert f"{found.id}@1" in REGISTRY


def test_the_limits_say_the_findings_are_leads_under_one_rule_pack() -> None:
    for metric_id in findings.FINDINGS_IDS:
        limits = entry(metric_id).limits
        assert "not confirmed defects" in limits
        assert "rule pack hash" in limits
        assert "rate" in limits


def test_the_parameters_equal_the_module_constants() -> None:
    for metric_id in findings.FINDINGS_IDS:
        parameters = entry(metric_id).methods[0].parameters
        assert parameters["command"] == [findings.OPENGREP, *findings.OPENGREP_COMMAND]
        assert parameters["timeout_min"] == findings.OPENGREP_TIMEOUT_MIN
        assert parameters["severity_from_level"] == dict(findings_sarif.LEVEL_SEVERITY)
        assert parameters["severity_thresholds"] == {
            "high": findings_sarif.HIGH_SCORE,
            "medium": findings_sarif.MEDIUM_SCORE,
        }
        assert parameters["security_tag"] == findings_sarif.SECURITY_TAG
        assert parameters["cwe_pattern"] == findings_sarif.CWE_PATTERN
