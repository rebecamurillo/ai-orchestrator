"""Tier 1b: duplication, function complexity and the dependency lookups of one repository.

The head content of the changed files is written under the scratch root, one level below the
folder each tool scans, and every figure counts only what the change added: a clone is counted
by the added lines inside its fragments, a function by an added line inside its range. A tool
that fails never stops the analysis; its signal reads `not run — {tool}: {reason}`.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.classify import classify
from orchestrator.application.analysis.dependencies import (
    OSV_SCANNER,
    diff_dependencies,
    lookup_dependencies,
)
from orchestrator.application.analysis.duplication import (
    common_dir,
    duplication_added,
    relative_sarif,
)
from orchestrator.application.analysis.inputs import RepositoryInputs, slug
from orchestrator.application.analysis.secrets import SARIF_MEDIA_TYPE
from orchestrator.application.analysis.summary import not_run
from orchestrator.application.analysis.tier1a import Count, added_line_numbers
from orchestrator.application.metrics.values import na
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.analysis_tools import AnalysisTools, ToolRun
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.package_lookup import PackageLookup
from orchestrator.domain.ports.workspace import Workspace

JSCPD = "jscpd"
LIZARD = "lizard"
JSCPD_COMMAND = ("--reporters", "sarif,json", "--output", "{dir}", "{files}")
LIZARD_COMMAND = ("--csv", "{files}")
LIZARD_COGNITIVE_COMMAND = ("--csv", "-Ecognitive", "{files}")
JSCPD_TIMEOUT_MIN = 10
LIZARD_TIMEOUT_MIN = 10
CYCLOMATIC_THRESHOLD = 15
COGNITIVE_THRESHOLD = 15
JSCPD_JSON = "jscpd-report.json"
JSCPD_SARIF = "jscpd-report.sarif"
HEAD_FILES = "files"
DUPLICATION = "code.duplication_added"
CYCLOMATIC = "code.functions_over_cyclomatic"
COGNITIVE = "code.functions_over_cognitive"
NOT_COVERED = na("language not covered")
#: `nloc, ccn, tokens, params, length, name@start-end@file, file, name, longname, start, end`,
#: then, with `-Ecognitive`, the cognitive value as a twelfth column.
LIZARD_CCN, LIZARD_FILE, LIZARD_START, LIZARD_END, LIZARD_COGNITIVE = 1, 6, 9, 10, 11
LIZARD_COLUMNS = 11


@dataclass(frozen=True)
class FunctionRow:
    path: str
    start: int
    end: int
    value: int


@dataclass(frozen=True)
class Tier1bResult:
    counts: tuple[Count, ...] = ()
    words: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[AnalysisArtifact, ...] = ()
    tool_versions: Mapping[str, str] = field(default_factory=dict)
    lookup_date: date | None = None
    vulnerability_db_date: date | None = None


def _failed(tool: str, reason: str) -> str:
    return not_run(f"{tool}: {reason}")


def _finished(tool: str, run: ToolRun) -> str | None:
    """The word for a tool that did not finish, else `None`."""
    if run.timed_out:
        return _failed(tool, "timed out")
    if run.exit != 0:
        first = run.stdout.strip().splitlines()[:1]
        return _failed(tool, ": ".join([f"exit {run.exit}", *first]))
    return None


def parse_lizard(csv_text: str, *, cognitive: bool) -> list[FunctionRow]:
    """The function rows of `lizard --csv`; a line that is not a data row is skipped."""
    rows: list[FunctionRow] = []
    for record in csv.reader(csv_text.splitlines()):
        column = LIZARD_COGNITIVE if cognitive else LIZARD_CCN
        if len(record) <= max(column, LIZARD_COLUMNS - 1):
            continue
        try:
            rows.append(
                FunctionRow(
                    record[LIZARD_FILE],
                    int(record[LIZARD_START]),
                    int(record[LIZARD_END]),
                    int(record[column]),
                )
            )
        except ValueError:
            continue
    return rows


def functions_over(
    rows: Sequence[FunctionRow], added: Mapping[str, frozenset[int]], threshold: int
) -> tuple[int, int]:
    """Changed functions above `threshold` and the worst value among them (0 when none)."""
    over = [
        row.value
        for row in rows
        if row.value > threshold and any(row.start <= n <= row.end for n in added.get(row.path, ()))
    ]
    return len(over), max(over, default=0)


def _function_counts(metric_id: str, over: tuple[int, int]) -> tuple[Count, Count]:
    return (
        Count(metric_id, "count", over[0], None, "sum"),
        Count(metric_id, "worst", over[1], None, "max"),
    )


@dataclass(frozen=True)
class _Scan:
    """What the scratch layout and the tools see of one repository."""

    scratch: Path
    relative: str
    tools: AnalysisTools
    scratch_root: Workspace


def _sarif_artifact(
    scan: _Scan, new_id: Callable[[], UUID], analysis_id: UUID
) -> AnalysisArtifact | None:
    """The jscpd SARIF, its `file://` URIs made relative; `None` when absent or unreadable."""
    sarif = scan.scratch_root.read(f"{scan.relative}.jscpd/{JSCPD_SARIF}")
    if sarif is None:
        return None
    try:
        body = relative_sarif(sarif).encode()
    except ValueError, AttributeError, TypeError:
        return None
    return AnalysisArtifact(
        id=new_id(), analysis_id=analysis_id, tool=JSCPD, media_type=SARIF_MEDIA_TYPE, body=body
    )


def _duplication(
    scan: _Scan,
    production: Sequence[str],
    added: Mapping[str, frozenset[int]],
    new_id: Callable[[], UUID],
    analysis_id: UUID,
) -> Tier1bResult:
    if not production:
        return Tier1bResult((Count(DUPLICATION, None, 0, "production"),))
    files = [f"{HEAD_FILES}/{path}" for path in production]
    args = [
        value
        for arg in JSCPD_COMMAND
        for value in (files if arg == "{files}" else [arg.format(dir=f"{scan.scratch}.jscpd")])
    ]
    run = scan.tools.run(JSCPD, args, Path(f"{scan.scratch}.head"), JSCPD_TIMEOUT_MIN)
    versions = {JSCPD: run.version}
    if (word := _finished(JSCPD, run)) is not None:
        return Tier1bResult(words={DUPLICATION: word}, tool_versions=versions)
    report = scan.scratch_root.read(f"{scan.relative}.jscpd/{JSCPD_JSON}")
    if report is None:
        return Tier1bResult(
            words={DUPLICATION: _failed(JSCPD, "no report")}, tool_versions=versions
        )
    try:
        count = duplication_added(report, added, common_dir(production))
    except ValueError, KeyError, TypeError, AttributeError:
        unreadable = _failed(JSCPD, "report unreadable")
        return Tier1bResult(words={DUPLICATION: unreadable}, tool_versions=versions)
    artifact = _sarif_artifact(scan, new_id, analysis_id)
    return Tier1bResult(
        (Count(DUPLICATION, None, count, "production"),),
        artifacts=(artifact,) if artifact is not None else (),
        tool_versions=versions,
    )


@dataclass(frozen=True)
class _Measure:
    """One lizard run: the signal it feeds, its command, its threshold."""

    metric: str
    command: Sequence[str]
    threshold: int
    cognitive: bool


CYCLOMATIC_MEASURE = _Measure(CYCLOMATIC, LIZARD_COMMAND, CYCLOMATIC_THRESHOLD, cognitive=False)
COGNITIVE_MEASURE = _Measure(
    COGNITIVE, LIZARD_COGNITIVE_COMMAND, COGNITIVE_THRESHOLD, cognitive=True
)


def _lizard(
    scan: _Scan,
    files: Sequence[str],
    added: Mapping[str, frozenset[int]],
    measure: _Measure,
) -> Tier1bResult:
    prefix = f"{scan.scratch}.head/{HEAD_FILES}/"
    absolute = [f"{prefix}{path}" for path in files]
    args = [value for arg in measure.command for value in (absolute if arg == "{files}" else [arg])]
    run = scan.tools.run(LIZARD, args, scan.scratch.parent, LIZARD_TIMEOUT_MIN)
    versions = {LIZARD: run.version}
    if (word := _finished(LIZARD, run)) is not None:
        return Tier1bResult(words={measure.metric: word}, tool_versions=versions)
    rows = [
        FunctionRow(r.path.removeprefix(prefix), r.start, r.end, r.value)
        for r in parse_lizard(run.stdout, cognitive=measure.cognitive)
    ]
    if measure.cognitive and not rows:
        return Tier1bResult(words={measure.metric: NOT_COVERED}, tool_versions=versions)
    counts = _function_counts(measure.metric, functions_over(rows, added, measure.threshold))
    return Tier1bResult(counts, tool_versions=versions)


def _functions(
    scan: _Scan, written: Sequence[str], added: Mapping[str, frozenset[int]]
) -> Tier1bResult:
    if not written:
        zeros = (*_function_counts(CYCLOMATIC, (0, 0)), *_function_counts(COGNITIVE, (0, 0)))
        return Tier1bResult(zeros)
    return _merge(
        [_lizard(scan, written, added, m) for m in (CYCLOMATIC_MEASURE, COGNITIVE_MEASURE)]
    )


def _merge(parts: Sequence[Tier1bResult]) -> Tier1bResult:
    return Tier1bResult(
        tuple(count for part in parts for count in part.counts),
        {metric: word for part in parts for metric, word in part.words.items()},
        tuple(artifact for part in parts for artifact in part.artifacts),
        {tool: version for part in parts for tool, version in part.tool_versions.items()},
        next((part.lookup_date for part in parts if part.lookup_date is not None), None),
        next(
            (
                part.vulnerability_db_date
                for part in parts
                if part.vulnerability_db_date is not None
            ),
            None,
        ),
    )


def _dependencies(  # noqa: PLR0913 — the repository's diff, the ports and what the lookups need
    prepared: RepositoryInputs,
    name_status: Sequence[NameStatus],
    refs: tuple[str, str],
    read: Callable[[str, str], str | None],
    write_lock: Callable[[str], Path],
    *,
    lookup: PackageLookup,
    lookups: bool,
    now: datetime,
    new_id: Callable[[], UUID],
) -> Tier1bResult:
    analysis = prepared.analysis
    diff = diff_dependencies(name_status, read, *refs)
    signals = lookup_dependencies(
        diff,
        lookup=lookup,
        lookups=lookups,
        registries=prepared.declaration.registries,
        now=now,
        write_lock=write_lock,
        new_id=new_id,
        analysis_id=analysis.id,
    )
    versions = {OSV_SCANNER: signals.osv_version} if signals.osv_version is not None else {}
    return Tier1bResult(
        signals.counts,
        signals.words,
        signals.artifacts,
        versions,
        signals.lookup_date,
        signals.vulnerability_db_date,
    )


def collect_tier1b(  # noqa: PLR0913 — the repository's inputs and the ports Tier 1b reads
    prepared: RepositoryInputs,
    *,
    git: Git,
    scratch_root: Workspace,
    tools: AnalysisTools,
    lookup: PackageLookup,
    lookups: bool,
    now: datetime,
    new_id: Callable[[], UUID],
) -> Tier1bResult:
    analysis = prepared.analysis
    scratch, base, head = prepared.scratch, analysis.base, analysis.head
    if scratch is None or base is None or head is None:
        return Tier1bResult()
    relative = f"{analysis.id}/{slug(analysis.repository_path)}"
    scan = _Scan(scratch, relative, tools, scratch_root)
    name_status = git.diff_name_status(scratch, base, head)
    added = added_line_numbers(git.diff_text(scratch, base, head, ()))

    def read(ref: str, path: str) -> str | None:
        """`None` for content that is not UTF-8 text (an image, say): no tool here reads it."""
        try:
            return git.read_file(scratch, ref, path)
        except UnicodeDecodeError:
            return None

    def write_lock(path: str) -> Path:
        scratch_root.write(f"{relative}.lock/{path}", read(head, path) or "")
        return Path(f"{scratch}.lock") / path

    written: list[str] = []
    for item in (item for item in name_status if item.status != "D"):
        text = read(head, item.path)
        if text is not None:
            scratch_root.write(f"{relative}.head/{HEAD_FILES}/{item.path}", text)
            written.append(item.path)
    production = [
        p for p in written if classify(p, prepared.declaration, hub=prepared.hub) == "production"
    ]
    return _merge(
        [
            _duplication(scan, production, added, new_id, analysis.id),
            _functions(scan, written, added),
            _dependencies(
                prepared,
                name_status,
                (base, head),
                read,
                write_lock,
                lookup=lookup,
                lookups=lookups,
                now=now,
                new_id=new_id,
            ),
        ]
    )
