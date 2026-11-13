"""The per-repository and Run summary of the Tier 1a counts (FR-21).

Counts are summed (or maxed, for a worst-of) over the repositories that ran; a rate is
recomputed from the summed counts and the summed denominators, never averaged. A word row
never carries a figure; a partial Run total keeps its figure (ARCHITECTURE §5.6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from orchestrator.application.analysis.tier1a import ROW_KEYS, TEST_CLASSES, Count
from orchestrator.application.metrics.values import PARTIAL, MetricValue, number, word

if TYPE_CHECKING:
    from orchestrator.application.analysis.signals import RepositorySignals

RATE_MIN_LINES = 50
SMALL_CHANGE_LINES = 200
PER_LINES = 100
NOT_RUN = "not run"
RAW_ONLY = "raw only"
SMALL_CHANGE = "small change"
SMALL_CHANGE_SOURCE = "small_change"
PER_100 = "per_100"
RUN = "run"
PRODUCTION_RATE_UNIT = "per 100 production lines"
TEST_RATE_UNIT = "per 100 test lines"
LINE_METRICS = ("code.lines_added", "code.lines_removed", "code.test_lines")
FILE_METRICS = ("code.files_touched", "code.test_files")
DUPLICATION = "code.duplication_added"
CENTS = Decimal("0.01")

Key = tuple[str, str | None]


def not_run(reason: str) -> str:
    return f"{NOT_RUN} — {reason}"


@dataclass(frozen=True)
class _Cell:
    """One raw row at one scope, with the denominators its rate divides by."""

    key: Key
    value: int | None
    word: str | None
    rate: str | None = None
    production: int = 0
    test: int = 0
    partial: tuple[int, int] | None = None


def _unit(metric_id: str) -> str:
    if metric_id in LINE_METRICS:
        return "lines"
    return "files" if metric_id in FILE_METRICS else "count"


def _denominators(counts: Sequence[Count]) -> tuple[int, int]:
    lines = {c.source: c.value for c in counts if c.metric_id == "code.lines_added"}
    return lines.get("production", 0), sum(lines.get(c, 0) for c in TEST_CLASSES)


def _first_line(output: str) -> str:
    first = output.strip().splitlines()[:1]
    return not_run(first[0]) if first else NOT_RUN


def _rows(
    cell: _Cell, scope_type: str, scope_key: str, repository: str | None
) -> list[MetricValue]:
    metric_id, source = cell.key
    fields: dict[str, object] = {
        "repository": repository,
        "source": source,
        "unit": _unit(metric_id),
    }
    if cell.value is None:
        return [word(metric_id, scope_type, scope_key, cell.word or NOT_RUN, **fields)]
    partial: dict[str, object] = {}
    if cell.partial is not None:
        partial = {"missing": PARTIAL, "partial_n": cell.partial[0], "partial_m": cell.partial[1]}
    rows = [number(metric_id, scope_type, scope_key, cell.value, **fields, **partial)]
    if cell.rate is not None:
        rows.append(_rate_row(cell, scope_type, scope_key, repository, partial))
    if metric_id == DUPLICATION and cell.production < SMALL_CHANGE_LINES:
        small = {**fields, "source": SMALL_CHANGE_SOURCE}
        rows.append(word(metric_id, scope_type, scope_key, SMALL_CHANGE, **small))
    return rows


def _rate_row(
    cell: _Cell,
    scope_type: str,
    scope_key: str,
    repository: str | None,
    partial: dict[str, object],
) -> MetricValue:
    metric_id, source = cell.key
    tests = cell.rate == "test"
    denominator = cell.test if tests else cell.production
    fields: dict[str, object] = {
        "repository": repository,
        "source": PER_100 if source is None else f"{source}:{PER_100}",
        "unit": TEST_RATE_UNIT if tests else PRODUCTION_RATE_UNIT,
    }
    if denominator < RATE_MIN_LINES:
        return word(metric_id, scope_type, scope_key, RAW_ONLY, **fields)
    rate = (Decimal(cell.value or 0) * PER_LINES / denominator).quantize(CENTS, ROUND_HALF_UP)
    return number(metric_id, scope_type, scope_key, rate, **fields, **partial)


def _repository_cells(signals: RepositorySignals) -> list[_Cell]:
    if signals.status == "failed":
        reason = _first_line(signals.output)
        return [_Cell(key, None, reason) for key in ROW_KEYS]
    production, test = _denominators(signals.counts)
    cells = [
        _Cell((c.metric_id, c.source), c.value, None, c.rate, production, test)
        for c in signals.counts
    ]
    return cells + [_Cell((m, None), None, w) for m, w in signals.words.items()]


def _run_cells(signals: Sequence[RepositorySignals]) -> list[_Cell]:
    ran = {s.path: {(c.metric_id, c.source): c for c in s.counts} for s in signals}
    per_repository = {s.path: _repository_cells(s) for s in signals}
    keys = list(dict.fromkeys(cell.key for cells in per_repository.values() for cell in cells))
    cells: list[_Cell] = []
    for key in keys:
        found = [
            (ran[s.path][key], _denominators(s.counts))
            for s in signals
            if s.status != "failed" and key in ran[s.path]
        ]
        if not found:
            words = {
                cell.word
                for cells_ in per_repository.values()
                for cell in cells_
                if cell.key == key
            }
            cells.append(_Cell(key, None, words.pop() if len(words) == 1 else NOT_RUN))
            continue
        values = [count.value for count, _ in found]
        first = found[0][0]
        cells.append(
            _Cell(
                key,
                max(values) if first.combine == "max" else sum(values),
                None,
                first.rate,
                sum(d[0] for _, d in found),
                sum(d[1] for _, d in found),
                (len(found), len(signals)) if len(found) < len(signals) else None,
            )
        )
    return cells


def summarise(signals: Sequence[RepositorySignals]) -> list[MetricValue]:
    """Repository rows in input order, then the Run rows; `[]` for no repository."""
    if not signals:
        return []
    values: list[MetricValue] = []
    for repository in signals:
        for cell in _repository_cells(repository):
            values += _rows(cell, "repository", repository.path, repository.path)
    for cell in _run_cells(signals):
        values += _rows(cell, "run", RUN, None)
    return values
