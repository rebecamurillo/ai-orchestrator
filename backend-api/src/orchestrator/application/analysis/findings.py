"""Possible security and bug findings: Opengrep over the changed files at base and at head.

Only the repository's own rules run, read at base and copied under the scratch root; no rule
pack is installed or fetched. A finding is new, unchanged or fixed by the match in
`findings_sarif` (ARCHITECTURE §7.3). A tool that fails never stops the analysis; the two
signals read `not run — opengrep: {reason}`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import UUID

from orchestrator.application.analysis.findings_sarif import (
    Finding,
    Matched,
    SarifUnreadable,
    match,
    parse_findings,
    with_baseline,
)
from orchestrator.application.analysis.inputs import RepositoryInputs, slug
from orchestrator.application.analysis.secrets import SARIF_MEDIA_TYPE
from orchestrator.application.analysis.summary import not_run
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.values import na
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.analysis_tools import AnalysisTools, ToolRun
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.workspace import Workspace

OPENGREP = "opengrep"
SECURITY = "code.findings_security"
BUG = "code.findings_bug"
FINDINGS_IDS = (SECURITY, BUG)
NO_RULES = na("no rules declared")
OPENGREP_TIMEOUT_MIN = 10
OPENGREP_COMMAND = ("scan", "--config", "{rules}", "--sarif-output", "{file}", "{files}")
SEVERITIES = ("high", "medium", "low")
FINDINGS_TOOL = "opengrep:findings"
JSON_MEDIA_TYPE = "application/json"
SCANNED_FILES = "files"
UNKNOWN_VERSION = "unknown"
Side = Literal["base", "head"]


@dataclass(frozen=True)
class FindingsResult:
    counts: tuple[Count, ...] = ()
    words: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[AnalysisArtifact, ...] = ()
    toolset: tuple[dict[str, Any], ...] = ()
    tool_versions: Mapping[str, str] = field(default_factory=dict)


class _Stop(Exception):
    """One word for both signals, and the version the run reported, if it ran."""

    def __init__(self, reason: str, version: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.version = version


def _words(reason: str) -> dict[str, str]:
    return dict.fromkeys(FINDINGS_IDS, not_run(f"{OPENGREP}: {reason}"))


def _rule_files(git: Git, scratch: Path, base: str, rules: str) -> dict[str, str]:
    """The repository's own rule files at base, by path; empty when it declares none there."""
    if PurePosixPath(rules).is_absolute() or ".." in PurePosixPath(rules).parts:
        return {}
    # The listing goes first: `git show ref:dir` answers a directory with its tree listing.
    listed = git.list_files(scratch, base, rules.rstrip("/") + "/")
    if not listed:
        single = git.read_file(scratch, base, rules)
        return {} if single is None else {rules: single}
    found: dict[str, str] = {}
    for path in listed:
        text = git.read_file(scratch, base, path)
        if text is not None:
            found[path] = text
    return found


def _pack_hash(files: Mapping[str, str]) -> str:
    pairs = sorted(
        [path, hashlib.sha256(text.encode()).hexdigest()] for path, text in files.items()
    )
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()


def _changed(name_status: Sequence[NameStatus]) -> tuple[list[str], list[str], dict[str, str]]:
    """Paths to scan at head and at base, and the base-to-head path of each rename."""
    head = [item.path for item in name_status if item.status != "D"]
    base: list[str] = []
    renames: dict[str, str] = {}
    for item in name_status:
        if item.status in ("R", "C") and item.old_path is not None:
            base.append(item.old_path)
            if item.status == "R":
                renames[item.old_path] = item.path
        elif item.status in ("M", "T", "D"):
            base.append(item.path)
    return head, base, renames


def _read_text(git: Git, scratch: Path, ref: str, path: str) -> str | None:
    try:
        return git.read_file(scratch, ref, path)
    except UnicodeDecodeError:
        return None


def _args(config: Path, report: Path, files: Sequence[str]) -> list[str]:
    targets = [f"{SCANNED_FILES}/{path}" for path in files]
    values: dict[str, list[str]] = {
        "{rules}": [str(config)],
        "{file}": [str(report)],
        "{files}": targets,
    }
    return [value for arg in OPENGREP_COMMAND for value in values.get(arg, [arg])]


def _finished(run: ToolRun) -> str | None:
    if run.timed_out:
        return "timed out"
    if run.exit != 0:
        first = run.stdout.strip().splitlines()[:1]
        return ": ".join([f"exit {run.exit}", *first])
    return None


@dataclass(frozen=True)
class _Side:
    sarif: str
    findings: list[Finding]
    version: str


def _scan(  # noqa: PLR0913 — one side's files, the rule copy and the ports
    side: Side,
    texts: Mapping[str, str],
    *,
    scratch: Path,
    relative: str,
    config: Path,
    renames: Mapping[str, str],
    scratch_root: Workspace,
    tools: AnalysisTools,
) -> _Side | None:
    if not texts:
        return None
    for path, text in texts.items():
        scratch_root.write(f"{relative}.sast-{side}/{SCANNED_FILES}/{path}", text)
    folder = Path(f"{scratch}.sast-{side}")
    run = tools.run(
        OPENGREP,
        _args(config, Path(f"{scratch}.sast-{side}.sarif"), sorted(texts)),
        folder,
        OPENGREP_TIMEOUT_MIN,
    )
    if (reason := _finished(run)) is not None:
        raise _Stop(reason, run.version)
    report = scratch_root.read(f"{relative}.sast-{side}.sarif")
    if report is None:
        raise _Stop("no report", run.version)
    try:
        found = parse_findings(
            report,
            root=str(folder),
            read_source=texts.get,
            renames=renames if side == "base" else {},
        )
    except SarifUnreadable:
        raise _Stop("report unreadable", run.version) from None
    return _Side(report, found, run.version)


def _counts(metric_id: str, kind: str, matched: Matched) -> tuple[Count, ...]:
    new = [f for f in matched.new if f.kind == kind]
    return (
        *(Count(metric_id, s, sum(f.severity == s for f in new), None) for s in SEVERITIES),
        Count(metric_id, "fixed", sum(f.kind == kind for f in matched.absent), None),
        Count(metric_id, "unchanged", sum(f.kind == kind for f in matched.unchanged), None),
    )


def _listing(matched: Matched) -> bytes:
    states = (("new", matched.new), ("unchanged", matched.unchanged), ("absent", matched.absent))
    rows = [
        {
            "kind": f.kind,
            "rule": f.rule_id,
            "path": f.path,
            "line": f.line,
            "severity": f.severity,
            "cwe": list(f.cwe),
            "state": state,
        }
        for state, findings in states
        for f in findings
    ]
    return json.dumps(rows, ensure_ascii=False).encode()


def collect_findings(
    prepared: RepositoryInputs,
    *,
    git: Git,
    scratch_root: Workspace,
    tools: AnalysisTools,
    new_id: Callable[[], UUID],
) -> FindingsResult:
    analysis = prepared.analysis
    scratch, base, head = prepared.scratch, analysis.base, analysis.head
    rules = prepared.declaration.sast_rules
    if scratch is None or base is None or head is None:
        return FindingsResult()
    if rules is None:
        return FindingsResult(words=dict.fromkeys(FINDINGS_IDS, NO_RULES))
    relative = f"{analysis.id}/{slug(analysis.repository_path)}"
    pack = _rule_files(git, scratch, base, rules)
    if not pack:
        return _stopped(_Stop(f"no rules at {rules}"), None, tools)
    for path, text in pack.items():
        scratch_root.write(f"{relative}.sast-rules/{path}", text)
    head_paths, base_paths, renames = _changed(git.diff_name_status(scratch, base, head))
    texts: dict[Side, dict[str, str]] = {"base": {}, "head": {}}
    wanted: tuple[tuple[Side, str, list[str]], ...] = (
        ("base", base, base_paths),
        ("head", head, head_paths),
    )
    for side, ref, paths in wanted:
        for path in paths:
            content = _read_text(git, scratch, ref, path)
            if content is not None:
                texts[side][path] = content
    config = Path(f"{scratch}.sast-rules") / rules
    pack_hash = _pack_hash(pack)
    try:
        sides = {
            side: _scan(
                side,
                texts[side],
                scratch=scratch,
                relative=relative,
                config=config,
                renames=renames,
                scratch_root=scratch_root,
                tools=tools,
            )
            for side in ("base", "head")
        }
    except _Stop as stop:
        return _stopped(stop, pack_hash, tools)
    return _result(
        sides["base"],
        sides["head"],
        pack_hash=pack_hash,
        tools=tools,
        ids=(analysis.id, new_id),
        root=f"{scratch}.sast-head",
    )


def _stopped(stop: _Stop, pack_hash: str | None, tools: AnalysisTools) -> FindingsResult:
    version = stop.version if stop.version is not None else tools.version(OPENGREP)
    record = {"tool": OPENGREP, "version": version, "rule_pack_hash": pack_hash}
    return FindingsResult(
        words=_words(stop.reason), toolset=(record,), tool_versions={OPENGREP: version}
    )


def _result(  # noqa: PLR0913 — both sides, the pack hash and what an artefact needs
    base: _Side | None,
    head: _Side | None,
    *,
    pack_hash: str,
    tools: AnalysisTools,
    ids: tuple[UUID, Callable[[], UUID]],
    root: str,
) -> FindingsResult:
    analysis_id, new_id = ids
    matched = match(base.findings if base else [], head.findings if head else [])
    ran = base or head
    version = ran.version if ran is not None else tools.version(OPENGREP)
    artifacts: tuple[AnalysisArtifact, ...] = ()
    if ran is not None:
        stored = with_baseline(
            head.sarif if head else None,
            base.sarif if base else None,
            matched,
            root=root,
        )
        artifacts = (
            AnalysisArtifact(
                id=new_id(),
                analysis_id=analysis_id,
                tool=OPENGREP,
                media_type=SARIF_MEDIA_TYPE,
                body=stored.encode(),
            ),
            AnalysisArtifact(
                id=new_id(),
                analysis_id=analysis_id,
                tool=FINDINGS_TOOL,
                media_type=JSON_MEDIA_TYPE,
                body=_listing(matched),
            ),
        )
    return FindingsResult(
        (*_counts(SECURITY, "security", matched), *_counts(BUG, "bug", matched)),
        {},
        artifacts,
        ({"tool": OPENGREP, "version": version, "rule_pack_hash": pack_hash},),
        {OPENGREP: version},
    )
