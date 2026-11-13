"""What the comparison says about static signals: toolsets, their fingerprints, the diff size.

Two analyses are comparable only when measured the same way (ARCHITECTURE §7.5); the fingerprint
is stored on each result version, so nothing is recomputed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from orchestrator.application.analysis.toolset import DECLARATION_HASH
from orchestrator.application.metrics.compare_views import ToolVersion
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.metric_results import StoredMetricValue

DECLARATION_TOOL = "orchestrator-analysis.yaml"
NOT_RUN = "not run"
HASH_LENGTH = 8
MINUS = "\N{MINUS SIGN}"
DIFF_METRICS = ("code.lines_added", "code.lines_removed", "code.files_touched")


def run_toolset(analyses: Sequence[Analysis]) -> list[ToolVersion]:
    """Per tool the distinct versions across the Run's analyses, then the declaration."""
    versions: dict[str, set[str]] = {}
    declarations: set[str] = set()
    for analysis in analyses:
        held = analysis.declaration_hash
        for record in analysis.toolset:
            if "tool" in record:
                versions.setdefault(str(record["tool"]), set()).add(str(record["version"]))
            else:
                held = record.get(DECLARATION_HASH) or held
        declarations.add((held or "")[:HASH_LENGTH] or "absent")
    found = [ToolVersion(tool, "/".join(sorted(v))) for tool, v in sorted(versions.items())]
    return [*found, ToolVersion(DECLARATION_TOOL, "/".join(sorted(declarations)))]


def fingerprints_differ(fingerprints: Iterable[str | None]) -> bool:
    return len({f for f in fingerprints if f is not None}) > 1


def _is_raw(value: StoredMetricValue) -> bool:
    source = value.source or ""
    return source != "small_change" and not source.endswith("per_100")


def diff_size_words(values: Sequence[StoredMetricValue], analysed: bool) -> str:
    """Added, removed and files touched from the raw run-scope rows, else a stored word."""
    if not analysed:
        return NOT_RUN
    totals: dict[str, int] = {}
    words: list[str] = []
    for value in values:
        if value.metric_id not in DIFF_METRICS or value.scope_type != "run" or not _is_raw(value):
            continue
        if value.value_num is not None:
            totals[value.metric_id] = totals.get(value.metric_id, 0) + int(value.value_num)
        else:
            words.append(value.missing or NOT_RUN)
    if not totals:
        return words[0] if words else NOT_RUN
    added, removed, files = (totals.get(metric, 0) for metric in DIFF_METRICS)
    return f"+{added} {MINUS}{removed} · {files} files"
