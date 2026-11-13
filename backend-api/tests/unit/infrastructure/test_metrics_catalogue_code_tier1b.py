"""The Tier 1b entries of `code.yaml` state what the code computes (epic 5 story 3)."""

from __future__ import annotations

from tests.unit.infrastructure.test_metrics_catalogue_code import entries, params

from orchestrator.application.analysis import dependencies, lockfiles, tier1b
from orchestrator.infrastructure.analysis import package_lookup


def missing_words(metric_id: str) -> list[str]:
    return list(entries()[metric_id].missing_words)


def test_the_dependency_parameters_equal_the_module_constants() -> None:
    changed = params("code.deps_changed")
    assert changed["lock_files"] == list(lockfiles.LOCK_ECOSYSTEM)
    assert changed["manifests"] == list(lockfiles.MANIFEST_ECOSYSTEM)
    assert params("code.deps_recent")["recent_days"] == dependencies.RECENT_DAYS == 30
    for metric_id in ("code.deps_not_in_registry", "code.deps_recent", "code.deps_licences"):
        assert params(metric_id)["registries"] == package_lookup.DEFAULT_REGISTRIES


def test_the_osv_parameters_equal_the_adapter_constants() -> None:
    vulns = params("code.deps_known_vulns")
    assert vulns["osv_command"] == list(package_lookup.OSV_COMMAND)
    assert vulns["osv_json_command"] == list(package_lookup.OSV_JSON_COMMAND)
    assert vulns["timeout_min"] == package_lookup.OSV_TIMEOUT_MIN
    assert vulns["lock_files"] == list(lockfiles.LOCK_ECOSYSTEM)


def test_the_duplication_and_function_parameters_equal_the_module_constants() -> None:
    duplication = params("code.duplication_added")
    assert duplication["jscpd_command"] == list(tier1b.JSCPD_COMMAND)
    assert duplication["timeout_min"] == tier1b.JSCPD_TIMEOUT_MIN
    cyclomatic = params("code.functions_over_cyclomatic")
    assert cyclomatic["lizard_command"] == list(tier1b.LIZARD_COMMAND)
    assert cyclomatic["threshold"] == tier1b.CYCLOMATIC_THRESHOLD
    assert cyclomatic["timeout_min"] == tier1b.LIZARD_TIMEOUT_MIN
    cognitive = params("code.functions_over_cognitive")
    assert cognitive["lizard_cognitive_command"] == list(tier1b.LIZARD_COGNITIVE_COMMAND)
    assert cognitive["threshold"] == tier1b.COGNITIVE_THRESHOLD
    for found in (cyclomatic, cognitive):
        assert found["combine"] == {"count": "sum", "worst": "max"}


def test_the_new_missing_words_are_declared() -> None:
    for metric_id in ("code.deps_not_in_registry", "code.deps_recent", "code.deps_licences"):
        assert "not checked" in missing_words(metric_id)
    assert "n/a" in missing_words("code.functions_over_cognitive")


def test_the_function_entries_state_the_sum_the_larger_and_no_rate() -> None:
    for metric_id in ("code.functions_over_cyclomatic", "code.functions_over_cognitive"):
        limits = entries()[metric_id].limits or ""
        assert "summed" in limits
        assert "larger" in limits
        assert "no rate" in limits
