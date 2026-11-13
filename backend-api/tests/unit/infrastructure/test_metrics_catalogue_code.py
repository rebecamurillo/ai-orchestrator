"""The shipped `code.yaml`: Tier 1a and 1b ids, labels, levels, parameters (story 5.2, AC8)."""

from __future__ import annotations

from orchestrator.application.analysis import classify, secrets, summary, tier1a
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.domain.ports.catalogue import CatalogueEntry
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue

TABLE = {
    "code.lines_added": ("lines added, by class", "H"),
    "code.lines_removed": ("lines removed, by class", "H"),
    "code.files_touched": ("files touched (added · modified · deleted)", "H"),
    "code.suppressions_added": ("suppressions added", "H"),
    "code.type_escapes_added": (
        "type escapes added, production and tests apart, each per 100 added lines of its own"
        " class (rev 3)",
        "H",
    ),
    "code.skip_focus_markers_added": ("skip and focus markers added", "H"),
    "code.preexisting_tests_changed": ("pre-existing tests changed", "H"),
    "code.preexisting_tests_deleted": ("pre-existing tests deleted", "H"),
    "code.test_files": ("test files added · modified · deleted, by class", "A"),
    "code.test_lines": ("test lines, by class", "A"),
    "code.test_cases_static": ("test cases opened (approximate)", "A"),
    "code.manifest_changes": ("dependency manifest changes", "A"),
    "code.possible_secrets": ("possible secrets added", "H"),
    "code.deps_changed": ("dependencies added · removed · upgraded", "H"),
    "code.deps_not_in_registry": ("dependencies not found in the registry", "H"),
    "code.deps_known_vulns": ("dependencies with known vulnerabilities", "H"),
    "code.deps_recent": ("dependencies published < 30 days before the analysis", "A"),
    "code.deps_licences": ("licences of added dependencies", "A"),
    "code.duplication_added": ("duplicated lines added", "A"),
    "code.functions_over_cyclomatic": ("functions above the cyclomatic threshold · worst", "A"),
    "code.functions_over_cognitive": ("functions above the cognitive threshold · worst", "A"),
}


def entries() -> dict[str, CatalogueEntry]:
    return {e.id: e for e in PackageCatalogue().entries() if e.group == "code"}


def params(metric_id: str) -> dict[str, object]:
    (method,) = entries()[metric_id].methods
    return dict(method.parameters)


def test_the_code_group_holds_exactly_the_twenty_one_ids_with_their_labels_and_levels() -> None:
    found = entries()
    assert set(found) == set(TABLE)
    for metric_id, (label, level) in TABLE.items():
        assert (found[metric_id].label, found[metric_id].level) == (label, level)


def test_every_entry_has_one_first_method_that_states_its_computation() -> None:
    for entry in entries().values():
        assert [m.n for m in entry.methods] == [1]
        assert entry.methods[0].description.strip()
        assert entry.scopes == ("run", "repository")
        assert entry.additive is False
        assert entry.fingerprint_group is True
        assert entry.limits and "rate" in entry.limits


def test_the_registry_still_equals_the_catalogued_first_methods() -> None:
    catalogued = {f"{e.id}@1" for e in PackageCatalogue().entries()}
    assert set(REGISTRY) == catalogued


def test_pattern_parameters_equal_the_module_constants() -> None:
    assert params("code.suppressions_added")["patterns"] == list(tier1a.SUPPRESSION_PATTERNS)
    assert params("code.type_escapes_added")["patterns"] == list(tier1a.TYPE_ESCAPE_PATTERNS)
    assert params("code.skip_focus_markers_added")["patterns"] == list(tier1a.SKIP_FOCUS_PATTERNS)
    assert params("code.test_cases_static")["openers"] == list(tier1a.TEST_CASE_OPENERS)
    manifest = params("code.manifest_changes")
    assert manifest["manifests"] == list(tier1a.MANIFEST_FILES)
    assert manifest["lock_files"] == list(classify.LOCK_FILES)
    command = params("code.possible_secrets")
    assert command["command"] == list(secrets.GITLEAKS_COMMAND)
    assert command["timeout_min"] == secrets.GITLEAKS_TIMEOUT_MIN
    assert command["redact"] is True
    assert command["added_files_folder"] == secrets.ADDED_FILES


def test_the_classifier_rules_are_parameters_of_lines_added() -> None:
    p = params("code.lines_added")
    assert p["precedence"] == list(classify.PRECEDENCE)
    assert p["generated"] == list(classify.GENERATED_PATTERNS)
    assert p["hub"] == list(classify.HUB_PATTERNS)
    assert p["e2e"] == list(classify.E2E_PATTERNS)
    assert p["unit"] == list(classify.UNIT_PATTERNS)
    assert p["unclassified"] == list(classify.UNCLASSIFIED_PATTERNS)
    assert p["docs"] == list(classify.DOCS_PATTERNS)
    assert p["configuration"] == list(classify.CONFIGURATION_PATTERNS)
    assert p["lock_files"] == list(classify.LOCK_FILES)


def test_the_thresholds_are_parameters() -> None:
    rated = params("code.suppressions_added")
    assert rated["rate_min_lines"] == summary.RATE_MIN_LINES
    assert rated["per_lines"] == summary.PER_LINES
    assert params("code.duplication_added")["small_change_lines"] == summary.SMALL_CHANGE_LINES
