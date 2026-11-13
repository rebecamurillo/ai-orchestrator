"""Tier 3: reports a workflow step wrote, imported once its template catalogued them.

A file is read only when a declared `metrics:` entry's `path` glob matches it at the analysis
head of the Run's own repository. One generic importer per format; a file no declaration claims
is reported as `not catalogued` and shows no figure (SPEC CAP-3, RM-2). Report files are the
measured repository's output and are untrusted: DTD markup is refused as in `tier2_reports`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.summary import not_run
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.tier2_reports import (
    ReportUnreadable,
    parse_coverage,
    parse_junit,
    parse_xml,
)
from orchestrator.application.metrics.values import na
from orchestrator.application.templates.step_metric_model import StepMetric
from orchestrator.domain.entities.run_records import ROOT_PATH
from orchestrator.domain.ports.git import Git

SARIF_LEVELS = ("error", "warning", "note", "none")
SARIF_DEFAULT_LEVEL = "warning"
JUNIT_SOURCES = ("passed", "failed", "errored", "skipped")
REPORT_SUFFIXES = (".xml", ".sarif", ".json")
ADDED_MODIFIED_RENAMED = ("A", "M", "R")
GLOB_CHARACTERS = "*?["
#: A committed report is untrusted: a non-UTF-8 file (`UnicodeDecodeError` is a `ValueError`) or
#: deeply nested JSON (`RecursionError`) must cost this file, never the repository's analysis.
UNREADABLE = (ValueError, RecursionError)
WHOLE_TREE = "."

Counts = dict[str, int]


@dataclass(frozen=True)
class StepResults:
    counts: tuple[Count, ...] = ()
    words: Mapping[str, str] = field(default_factory=dict)
    not_catalogued: tuple[str, ...] = ()


def sniff(text: str) -> str | None:
    """The format of a report text, or `None` when it is none of the four."""
    stripped = text.lstrip()
    if stripped.startswith("<"):
        try:
            tag = parse_xml(text).tag
        except ReportUnreadable:
            return None
        return {"testsuites": "junit", "testsuite": "junit", "coverage": "cobertura"}.get(
            tag, "jacoco" if tag == "report" else None
        )
    try:
        document = json.loads(text)
    except UNREADABLE:
        return None
    if isinstance(document, dict) and isinstance(document.get("runs"), list):
        return "sarif" if isinstance(document.get("version"), str) else None
    return None


def import_junit(texts: Sequence[str]) -> Counts:
    counts = dict.fromkeys(JUNIT_SOURCES, 0)
    token = {"passed": "passed", "failed": "failed", "error": "errored", "skipped": "skipped"}
    for text in texts:
        for case in parse_junit(text):
            counts[token[case.outcome]] += 1
    return counts


def import_coverage(texts: Sequence[str]) -> Counts:
    covered = instrumented = 0
    for text in texts:
        for per_file in parse_coverage(text).lines.values():
            instrumented += len(per_file)
            covered += sum(per_file.values())
    return {"covered": covered, "instrumented": instrumented}


def _sarif_levels(text: str) -> list[str]:
    try:
        document = json.loads(text)
    except UNREADABLE as error:
        raise ReportUnreadable(f"not JSON: {error}") from error
    runs = document.get("runs") if isinstance(document, dict) else None
    if not isinstance(runs, list):
        raise ReportUnreadable("not a SARIF document: no runs")
    levels: list[str] = []
    for run in runs:
        results = run.get("results", []) if isinstance(run, dict) else None
        if not isinstance(results, list):
            raise ReportUnreadable("SARIF run holds no results list")
        for result in results:
            level = result.get("level", SARIF_DEFAULT_LEVEL) if isinstance(result, dict) else None
            if level not in SARIF_LEVELS:
                raise ReportUnreadable(f"SARIF result level {level!r}")
            levels.append(level)
    return levels


def import_sarif(texts: Sequence[str]) -> Counts:
    counts = dict.fromkeys(SARIF_LEVELS, 0)
    for text in texts:
        for level in _sarif_levels(text):
            counts[level] += 1
    return counts


IMPORTERS: Mapping[str, Callable[[Sequence[str]], Counts]] = {
    "junit": import_junit,
    "cobertura": import_coverage,
    "jacoco": import_coverage,
    "sarif": import_sarif,
}


def _prefix(glob: str) -> str:
    """The literal directories a glob starts with; the file name segment is never one."""
    kept: list[str] = []
    for segment in glob.split("/")[:-1]:
        if any(character in segment for character in GLOB_CHARACTERS):
            break
        kept.append(segment)
    return "/".join(kept) or WHOLE_TREE


def matching_files(git: Git, scratch: Any, head: str, glob: str) -> list[str]:
    listed = git.list_files(scratch, head, _prefix(glob))
    return sorted(path for path in listed if PurePosixPath(path).full_match(glob))


def _first_line(error: Exception) -> str:
    lines = str(error).splitlines()
    return lines[0] if lines else type(error).__name__


def _import_one(
    git: Git, scratch: Any, head: str, metric: StepMetric
) -> tuple[list[Count], dict[str, str]]:
    paths = matching_files(git, scratch, head, metric.path)
    if not paths:
        return [], {metric.entry.id: na(f"no file matches {metric.path}")}
    try:
        texts = [git.read_file(scratch, head, path) or "" for path in paths]
        counts = IMPORTERS[metric.format](texts)
    except UNREADABLE as error:
        reason = f"{metric.format} report unreadable: {_first_line(error)}"
        return [], {metric.entry.id: not_run(reason)}
    return [Count(metric.entry.id, source, value, None) for source, value in counts.items()], {}


def _not_catalogued(
    git: Git, scratch: Any, base: str, head: str, declared: Sequence[StepMetric]
) -> tuple[str, ...]:
    found: list[str] = []
    for changed in git.diff_name_status(scratch, base, head):
        path = changed.path
        if changed.status not in ADDED_MODIFIED_RENAMED or not path.endswith(REPORT_SUFFIXES):
            continue
        if any(PurePosixPath(path).full_match(metric.path) for metric in declared):
            continue
        try:
            text = git.read_file(scratch, head, path)
        except UNREADABLE:
            continue
        if text is not None and sniff(text) is not None:
            found.append(path)
    return tuple(sorted(found))


def collect_step_results(
    prepared: RepositoryInputs, *, git: Git, declared: Sequence[StepMetric]
) -> StepResults:
    """Only the Run's own repository: a member repository's files are not the template's."""
    analysis = prepared.analysis
    scratch, base, head = prepared.scratch, analysis.base, analysis.head
    if (
        analysis.repository_path != ROOT_PATH
        or analysis.status == "failed"
        or scratch is None
        or base is None
        or head is None
    ):
        return StepResults()
    counts: list[Count] = []
    words: dict[str, str] = {}
    for metric in declared:
        found, missing = _import_one(git, scratch, head, metric)
        counts += found
        words.update(missing)
    return StepResults(tuple(counts), words, _not_catalogued(git, scratch, base, head, declared))
