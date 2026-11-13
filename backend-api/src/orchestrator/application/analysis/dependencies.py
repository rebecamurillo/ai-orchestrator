"""The dependencies a change adds, removes and upgrades, and what the lookups say of the added ones.

Lock files decide when one is present at head in the folder; a changed manifest is read only
where no supported lock file exists. Nothing but the ecosystem, the name and the version goes
to a lookup (RM-6), and the private registry URL of a declaration is never echoed into a word.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from orchestrator.application.analysis.lockfiles import (
    LOCK_ECOSYSTEM,
    MANIFEST_ECOSYSTEM,
    ParsedDeps,
    parse_lock,
    parse_manifest,
)
from orchestrator.application.analysis.secrets import SARIF_MEDIA_TYPE
from orchestrator.application.analysis.summary import not_run
from orchestrator.application.analysis.tier1a import Count
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.package_lookup import (
    LookupUnavailable,
    PackageLookup,
    PackageMeta,
)

RECENT_DAYS = 30
OSV_SCANNER = "osv-scanner"
DEPENDENCIES_TOOL = "dependencies"
NOT_CHECKED = "not checked"
NONE_DECLARED = "none declared"

CHANGED = "code.deps_changed"
NOT_IN_REGISTRY = "code.deps_not_in_registry"
KNOWN_VULNS = "code.deps_known_vulns"
RECENT = "code.deps_recent"
LICENCES = "code.deps_licences"
METADATA_IDS = (NOT_IN_REGISTRY, RECENT, LICENCES)
LOOKUP_IDS = (NOT_IN_REGISTRY, KNOWN_VULNS, RECENT, LICENCES)

LOOKUPS_OFF = not_run("lookups off")
REGISTRY_UNREACHABLE = not_run("registry unreachable")
NO_LOCK_FILE = not_run("no lock file")

Read = Callable[[str, str], str | None]
MetaKey = tuple[str, str, str]


def not_checked(reason: str) -> str:
    return f"{NOT_CHECKED} — {reason}"


@dataclass(frozen=True)
class DepChange:
    ecosystem: str
    name: str
    before: frozenset[str]
    after: frozenset[str]


@dataclass(frozen=True)
class DependencyDiff:
    added: tuple[DepChange, ...] = ()
    removed: tuple[DepChange, ...] = ()
    upgraded: tuple[DepChange, ...] = ()
    lock_paths: tuple[str, ...] = ()
    #: Some added dependency was read from a manifest alone (no lock file to scan for it).
    manifest_only: bool = False
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencySignals:
    counts: tuple[Count, ...] = ()
    words: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[AnalysisArtifact, ...] = ()
    osv_version: str | None = None
    lookup_date: date | None = None
    vulnerability_db_date: date | None = None


def _folder(path: str) -> str:
    return str(PurePosixPath(path).parent)


def _join(folder: str, name: str) -> str:
    return name if folder == "." else f"{folder}/{name}"


def _compare(
    ecosystem: str, before: Mapping[str, frozenset[str]], after: Mapping[str, frozenset[str]]
) -> tuple[list[DepChange], list[DepChange], list[DepChange]]:
    added = [DepChange(ecosystem, n, frozenset(), v) for n, v in after.items() if n not in before]
    removed = [DepChange(ecosystem, n, v, frozenset()) for n, v in before.items() if n not in after]
    upgraded = [
        DepChange(ecosystem, n, before[n], v)
        for n, v in after.items()
        if n in before and before[n] != v
    ]
    return added, removed, upgraded


def _lock_pairs(
    changed: Sequence[NameStatus], read: Read, base: str, head: str
) -> tuple[list[tuple[str, ParsedDeps, ParsedDeps]], list[str]]:
    pairs: list[tuple[str, ParsedDeps, ParsedDeps]] = []
    lock_paths: list[str] = []
    for item in changed:
        name = PurePosixPath(item.path).name
        if name not in LOCK_ECOSYSTEM:
            continue
        text = read(head, item.path)
        if text is not None:
            lock_paths.append(item.path)
        before = parse_lock(name, read(base, item.old_path or item.path))
        pairs.append((LOCK_ECOSYSTEM[name], before, parse_lock(name, text)))
    return pairs, lock_paths


def _manifest_pairs(
    changed: Sequence[NameStatus], read: Read, base: str, head: str
) -> list[tuple[str, ParsedDeps, ParsedDeps]]:
    """Manifests only in folders where no supported lock file exists at head."""
    pairs: list[tuple[str, ParsedDeps, ParsedDeps]] = []
    for item in changed:
        name = PurePosixPath(item.path).name
        if name not in MANIFEST_ECOSYSTEM:
            continue
        folder = _folder(item.path)
        if any(read(head, _join(folder, lock)) is not None for lock in LOCK_ECOSYSTEM):
            continue
        before = parse_manifest(name, read(base, item.old_path or item.path))
        pairs.append(
            (MANIFEST_ECOSYSTEM[name], before, parse_manifest(name, read(head, item.path)))
        )
    return pairs


def diff_dependencies(
    changed: Sequence[NameStatus], read: Read, base: str, head: str
) -> DependencyDiff:
    """Added, removed and upgraded dependencies; `read(ref, path)` is the file's text or `None`."""
    pairs, lock_paths = _lock_pairs(changed, read, base, head)
    manifests = _manifest_pairs(changed, read, base, head)
    added: list[DepChange] = []
    removed: list[DepChange] = []
    upgraded: list[DepChange] = []
    for ecosystem, before, after in [*pairs, *manifests]:
        found = _compare(ecosystem, before.packages, after.packages)
        added += found[0]
        removed += found[1]
        upgraded += found[2]
    # Any added dependency read from a manifest has no lock file to scan, even when another
    # folder's lock file is scanned: a figure would count it as clean.
    from_manifest = any(
        _compare(ecosystem, before.packages, after.packages)[0]
        for ecosystem, before, after in manifests
    )
    problems = tuple(
        parsed.problem
        for _, before, after in [*pairs, *manifests]
        for parsed in (before, after)
        if parsed.problem is not None
    )
    return DependencyDiff(
        tuple(added),
        tuple(removed),
        tuple(upgraded),
        tuple(lock_paths),
        from_manifest,
        problems,
    )


def _version(change: DepChange) -> str:
    """The one head version, else the highest string."""
    return max(change.after)


def _is_recent(meta: PackageMeta, now: datetime) -> bool:
    return meta.first_published is not None and meta.first_published > now - timedelta(
        days=RECENT_DAYS
    )


@dataclass
class _Metadata:
    found: dict[MetaKey, PackageMeta] = field(default_factory=dict)
    private_refused: list[str] = field(default_factory=list)
    public_refused: bool = False

    @property
    def word(self) -> str | None:
        """Private registry did not answer, then public registry unreachable."""
        if self.private_refused:
            return not_checked(f"{self.private_refused[0]} private registry did not answer")
        return REGISTRY_UNREACHABLE if self.public_refused else None


def _fetch_metadata(
    added: Sequence[DepChange], lookup: PackageLookup, registries: Mapping[str, str]
) -> _Metadata:
    result = _Metadata()
    stopped: set[str] = set()
    for change in added:
        key = (change.ecosystem, change.name, _version(change))
        if change.ecosystem in stopped or key in result.found:
            continue
        registry = registries.get(change.ecosystem)
        try:
            result.found[key] = lookup.metadata(*key, registry)
        except LookupUnavailable:
            stopped.add(change.ecosystem)
            if registry is None:
                result.public_refused = True
            else:
                result.private_refused.append(change.ecosystem)
    return result


def _metadata_signals(meta: _Metadata, now: datetime) -> tuple[list[Count], dict[str, str]]:
    if (word := meta.word) is not None:
        return [], dict.fromkeys(METADATA_IDS, word)
    found = list(meta.found.values())
    existing = [m for m in found if m.exists]
    licences = [m.licence or NONE_DECLARED for m in existing]
    counts = [
        Count(NOT_IN_REGISTRY, None, len(found) - len(existing), "production"),
        Count(RECENT, None, sum(_is_recent(m, now) for m in existing), "production"),
    ]
    if licences:
        counts += [
            Count(LICENCES, n, licences.count(n), "production") for n in sorted(set(licences))
        ]
    else:
        counts.append(Count(LICENCES, None, 0, "production"))
    return counts, {}


@dataclass(frozen=True)
class _Vulns:
    pairs: frozenset[tuple[str, str]] = frozenset()
    sarif: bytes | None = None
    version: str | None = None
    word: str | None = None


def _merged_sarif(documents: Sequence[bytes]) -> bytes | None:
    parsed: list[dict[str, Any]] = []
    for body in documents:
        try:
            document = json.loads(body)
        except ValueError:
            continue
        if isinstance(document, dict):
            parsed.append(document)
    if not parsed:
        return None
    runs = [run for document in parsed for run in document.get("runs", [])]
    return json.dumps({**parsed[0], "runs": runs}, ensure_ascii=False).encode()


def _scan(diff: DependencyDiff, lookup: PackageLookup, write_lock: Callable[[str], Path]) -> _Vulns:
    pairs: set[tuple[str, str]] = set()
    documents: list[bytes] = []
    version = ""
    try:
        for path in diff.lock_paths:
            report = lookup.vulnerabilities(write_lock(path))
            pairs |= report.vulnerable
            documents.append(report.sarif)
            version = report.version
    except LookupUnavailable as error:
        return _Vulns(word=not_run(error.reason))
    return _Vulns(frozenset(pairs), _merged_sarif(documents), version)


def _detail(
    change: DepChange, kind: str, meta: PackageMeta | None, vulns: _Vulns, now: datetime
) -> dict[str, Any]:
    """`null` for what was not looked up."""
    scanned = kind == "added" and vulns.version is not None
    published = meta.first_published if meta is not None else None
    return {
        "ecosystem": change.ecosystem,
        "name": change.name,
        "change": kind,
        "before": sorted(change.before),
        "after": sorted(change.after),
        "exists": meta.exists if meta is not None else None,
        "first_published": published.isoformat() if published is not None else None,
        "recent": _is_recent(meta, now) if meta is not None and meta.exists else None,
        "licence": meta.licence if meta is not None else None,
        "vulnerable": (change.name, _version(change)) in vulns.pairs if scanned else None,
        "looked_up_at": now.date().isoformat() if meta is not None or scanned else None,
    }


def _artifact(
    analysis_id: UUID, new_id: Callable[[], UUID], tool: str, media_type: str, body: bytes
) -> AnalysisArtifact:
    return AnalysisArtifact(
        id=new_id(), analysis_id=analysis_id, tool=tool, media_type=media_type, body=body
    )


def lookup_dependencies(  # noqa: PLR0913 — the diff, the ports and what the lookups need
    diff: DependencyDiff,
    *,
    lookup: PackageLookup,
    lookups: bool,
    registries: Mapping[str, str],
    now: datetime,
    write_lock: Callable[[str], Path],
    new_id: Callable[[], UUID],
    analysis_id: UUID,
) -> DependencySignals:
    """`write_lock(path)` writes the head lock file where the scanner can read it."""
    if diff.problems:
        return DependencySignals(
            words=dict.fromkeys((CHANGED, *LOOKUP_IDS), not_run(diff.problems[0]))
        )
    counts = [
        Count(CHANGED, "added", len(diff.added), "production"),
        Count(CHANGED, "removed", len(diff.removed), "production"),
        Count(CHANGED, "upgraded", len(diff.upgraded), "production"),
    ]
    if not lookups:
        return DependencySignals(tuple(counts), dict.fromkeys(LOOKUP_IDS, LOOKUPS_OFF))
    meta = _fetch_metadata(diff.added, lookup, registries)
    meta_counts, words = _metadata_signals(meta, now)
    counts += meta_counts
    vulns = _Vulns()
    if not diff.added:
        counts.append(Count(KNOWN_VULNS, None, 0, "production"))
    elif diff.manifest_only:
        words[KNOWN_VULNS] = NO_LOCK_FILE
    else:
        vulns = _scan(diff, lookup, write_lock)
        if vulns.word is not None:
            words[KNOWN_VULNS] = vulns.word
        else:
            hits = sum((c.name, _version(c)) in vulns.pairs for c in diff.added)
            counts.append(Count(KNOWN_VULNS, None, hits, "production"))
    artifacts: list[AnalysisArtifact] = []
    if vulns.sarif is not None:
        artifacts.append(_artifact(analysis_id, new_id, OSV_SCANNER, SARIF_MEDIA_TYPE, vulns.sarif))
    rows = [
        *(
            _detail(c, "added", meta.found.get((c.ecosystem, c.name, _version(c))), vulns, now)
            for c in diff.added
        ),
        *(_detail(c, "removed", None, vulns, now) for c in diff.removed),
        *(_detail(c, "upgraded", None, vulns, now) for c in diff.upgraded),
    ]
    if rows:
        body = json.dumps(rows, ensure_ascii=False).encode()
        artifacts.append(
            _artifact(analysis_id, new_id, DEPENDENCIES_TOOL, "application/json", body)
        )
    today = now.date()
    return DependencySignals(
        tuple(counts),
        words,
        tuple(artifacts),
        vulns.version,
        today if meta.found or vulns.version is not None else None,
        today if vulns.version is not None else None,
    )
