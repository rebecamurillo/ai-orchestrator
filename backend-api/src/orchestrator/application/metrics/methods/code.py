"""Part C static-signal methods: the per-repository and Run rows of the Tier 1 counts.

Every `code.*` id answers from the same summary of the repositories' signals; the Tier 1b ids
return nothing until a calculation feeds their counts.
"""

from __future__ import annotations

from orchestrator.application.analysis.summary import summarise
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import Method, register
from orchestrator.application.metrics.values import MetricValue

CODE_IDS = (
    "code.lines_added",
    "code.lines_removed",
    "code.files_touched",
    "code.suppressions_added",
    "code.type_escapes_added",
    "code.skip_focus_markers_added",
    "code.preexisting_tests_changed",
    "code.preexisting_tests_deleted",
    "code.test_files",
    "code.test_lines",
    "code.test_cases_static",
    "code.manifest_changes",
    "code.possible_secrets",
    "code.deps_changed",
    "code.deps_not_in_registry",
    "code.deps_known_vulns",
    "code.deps_recent",
    "code.deps_licences",
    "code.duplication_added",
    "code.functions_over_cyclomatic",
    "code.functions_over_cognitive",
)


def _method(metric_id: str) -> Method:
    def compute(inputs: RunInputs) -> list[MetricValue]:
        return [v for v in summarise(inputs.code) if v.metric_id == metric_id]

    return compute


for _id in CODE_IDS:
    register(f"{_id}@1")(_method(_id))
