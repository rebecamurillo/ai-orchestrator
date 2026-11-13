"""The `code.*@1` methods over the repository signals a calculation carries (story 5.2)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.compute import compute
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.methods.code import CODE_IDS
from tests.unit.application.metrics_builders import make_inputs

TIER_1A_AND_1B = (
    "code.lines_added code.lines_removed code.files_touched code.suppressions_added "
    "code.type_escapes_added code.skip_focus_markers_added code.preexisting_tests_changed "
    "code.preexisting_tests_deleted code.test_files code.test_lines code.test_cases_static "
    "code.manifest_changes code.possible_secrets code.deps_changed code.deps_not_in_registry "
    "code.deps_known_vulns code.deps_recent code.deps_licences code.duplication_added "
    "code.functions_over_cyclomatic code.functions_over_cognitive"
).split()


def signals(path: str, lines: int, suppressions: int) -> RepositorySignals:
    return RepositorySignals(
        path,
        "ok",
        "",
        (
            Count("code.lines_added", "production", lines, None),
            Count("code.suppressions_added", None, suppressions, "production"),
        ),
        {},
        (),
        {},
    )


def test_the_twenty_one_ids_are_registered_as_first_methods() -> None:
    assert sorted(CODE_IDS) == sorted(TIER_1A_AND_1B)
    assert len(CODE_IDS) == 21
    assert all(f"{i}@1" in REGISTRY for i in CODE_IDS)


def test_repository_signals_become_repository_and_run_values() -> None:
    inputs = replace(make_inputs([], []), code=(signals("a", 60, 2), signals("b", 40, 1)))
    values = [v for v in compute(inputs) if v.metric_id.startswith("code.")]
    assert {v.scope_type for v in values} == {"repository", "run"}
    assert all(v.method_id == f"{v.metric_id}@1" for v in values)
    run = [v for v in values if v.scope_type == "run" and v.metric_id == "code.suppressions_added"]
    assert next(v.value_num for v in run if v.source is None) == 3


def test_no_signals_no_code_values() -> None:
    assert [v for v in compute(make_inputs([], [])) if v.metric_id.startswith("code.")] == []
