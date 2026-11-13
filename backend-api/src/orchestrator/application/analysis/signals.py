"""What one repository's analysis yields before the summary: counts, words, artefacts.

`SUMMARY_TOOL` is the `analysis_artifact` tool name story 4 keeps the pending summary
under (ARCHITECTURE §7.3, one JSON summary per repository).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from orchestrator.application.analysis.inputs import RepositoryInputs, slug
from orchestrator.application.analysis.secrets import GITLEAKS, scan_secrets
from orchestrator.application.analysis.tier1a import Count, added_lines, count_tier1a
from orchestrator.application.analysis.tier1b import collect_tier1b
from orchestrator.application.analysis.toolset import TOOLS, toolset_records, with_toolset
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact, AnalysisStatus
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.analysis_tools import AnalysisTools
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.package_lookup import PackageLookup
from orchestrator.domain.ports.workspace import Workspace

SUMMARY_TOOL = "summary"
SECRETS_ID = "code.possible_secrets"


@dataclass(frozen=True)
class RepositorySignals:
    """`words` maps a metric id to the word standing in for a figure that could not be read."""

    path: str
    status: AnalysisStatus
    output: str
    counts: tuple[Count, ...]
    words: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[AnalysisArtifact, ...] = ()
    tool_versions: Mapping[str, str] = field(default_factory=dict)


def collect_tier1a(
    prepared: RepositoryInputs,
    *,
    git: Git,
    scratch_root: Workspace,
    tools: AnalysisTools,
    new_id: Callable[[], UUID],
) -> RepositorySignals:
    analysis = prepared.analysis
    scratch, base, head = prepared.scratch, analysis.base, analysis.head
    if analysis.status == "failed" or scratch is None or base is None or head is None:
        return RepositorySignals(analysis.repository_path, analysis.status, analysis.output, ())
    text = git.diff_text(scratch, base, head, ())
    counts = count_tier1a(
        git.diff_numstat(scratch, base, head),
        git.diff_name_status(scratch, base, head),
        text,
        prepared.declaration,
        hub=prepared.hub,
    )
    secrets = scan_secrets(
        added_lines(text),
        scratch_root=scratch_root,
        scratch_path=scratch,
        relative=f"{analysis.id}/{slug(analysis.repository_path)}",
        tools=tools,
        analysis_id=analysis.id,
        new_id=new_id,
    )
    found = Count(SECRETS_ID, None, secrets.count or 0, "production")
    return RepositorySignals(
        analysis.repository_path,
        analysis.status,
        analysis.output,
        (*counts, found) if secrets.count is not None else counts,
        {SECRETS_ID: secrets.missing} if secrets.missing is not None else {},
        (secrets.artifact,) if secrets.artifact is not None else (),
        {GITLEAKS: secrets.version} if secrets.version else {},
    )


def collect_signals(  # noqa: PLR0913 — the repository's inputs and every port the two tiers read
    prepared: RepositoryInputs,
    *,
    git: Git,
    scratch_root: Workspace,
    tools: AnalysisTools,
    lookup: PackageLookup,
    lookups: bool,
    now: datetime,
    new_id: Callable[[], UUID],
) -> tuple[Analysis, RepositorySignals]:
    """Tiers 1a and 1b of one repository, and the analysis stamped with its toolset."""
    analysis = prepared.analysis
    installed = {tool: tools.version(tool) for tool in TOOLS}
    first = collect_tier1a(prepared, git=git, scratch_root=scratch_root, tools=tools, new_id=new_id)
    if analysis.status == "failed" or prepared.scratch is None:
        records = toolset_records(
            installed,
            vulnerability_db_date=None,
            lookup_date=None,
            declaration_hash=analysis.declaration_hash,
        )
        return with_toolset(analysis, records), first
    second = collect_tier1b(
        prepared,
        git=git,
        scratch_root=scratch_root,
        tools=tools,
        lookup=lookup,
        lookups=lookups,
        now=now,
        new_id=new_id,
    )
    merged = replace(
        first,
        counts=(*first.counts, *second.counts),
        words={**first.words, **second.words},
        artifacts=(*first.artifacts, *second.artifacts),
        tool_versions={**first.tool_versions, **second.tool_versions},
    )
    records = toolset_records(
        installed,
        vulnerability_db_date=second.vulnerability_db_date,
        lookup_date=second.lookup_date,
        declaration_hash=analysis.declaration_hash,
    )
    return with_toolset(analysis, records), merged


def store_signals(repo: AnalysisRepository, analysis: Analysis, signals: RepositorySignals) -> None:
    """The analysis row first: an artefact refers to it."""
    repo.add(analysis)
    for artifact in signals.artifacts:
        repo.add_artifact(artifact)


def signals_to_json(signals: RepositorySignals) -> bytes:
    """Artefacts are left out: they are stored on their own."""
    document = {
        "path": signals.path,
        "status": signals.status,
        "output": signals.output,
        "counts": [[c.metric_id, c.source, c.value, c.rate, c.combine] for c in signals.counts],
        "words": dict(signals.words),
        "tool_versions": dict(signals.tool_versions),
    }
    return json.dumps(document, ensure_ascii=False).encode()


def signals_from_json(body: bytes) -> RepositorySignals:
    document: dict[str, Any] = json.loads(body)
    return RepositorySignals(
        path=document["path"],
        status=cast("AnalysisStatus", document["status"]),
        output=document["output"],
        counts=tuple(
            Count(
                m,
                s,
                v,
                cast("Literal['production', 'test'] | None", r),
                cast("Literal['sum', 'max']", c),
            )
            for m, s, v, r, c in document["counts"]
        ),
        words=document["words"],
        artifacts=(),
        tool_versions=document["tool_versions"],
    )
