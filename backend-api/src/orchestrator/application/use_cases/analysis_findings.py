"""Read the stored opengrep findings listing of an analysis (epic 6 story 4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from orchestrator.application.analysis.findings import FINDINGS_TOOL, JSON_MEDIA_TYPE, SEVERITIES
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class FindingRow:
    kind: str
    rule: str
    path: str
    line: int | None
    severity: str
    cwe: tuple[str, ...]
    state: str


KINDS = ("security", "bug")
STATES = ("new", "unchanged", "absent")


def _row(raw: Any) -> FindingRow:
    line = raw["line"]
    if (
        raw["kind"] not in KINDS
        or raw["severity"] not in SEVERITIES
        or raw["state"] not in STATES
        or not (line is None or (isinstance(line, int) and not isinstance(line, bool)))
        or not all(isinstance(c, str) for c in raw["cwe"])
        or not isinstance(raw["rule"], str)
        or not isinstance(raw["path"], str)
    ):
        raise ValueError("finding row outside the listing's shape")
    return FindingRow(
        kind=raw["kind"],
        rule=raw["rule"],
        path=raw["path"],
        line=raw["line"],
        severity=raw["severity"],
        cwe=tuple(raw["cwe"]),
        state=raw["state"],
    )


def read_findings(
    analyses: AnalysisRepository, uow: UnitOfWork, run_id: UUID, analysis_id: UUID
) -> list[FindingRow]:
    """The listing opengrep stored for the analysis; no partial answer for a malformed one."""
    with uow:
        analysis = analyses.get(analysis_id)
        if analysis is None or analysis.run_id != run_id:
            raise NotFound(f"run {run_id} has no analysis {analysis_id}")
        artifact = analyses.artifact(analysis_id, FINDINGS_TOOL)
        refusal = NotFound(f"analysis {analysis_id} has no findings listing")
        if artifact is None or artifact.media_type != JSON_MEDIA_TYPE:
            raise refusal
        try:
            body = json.loads(artifact.body)
            if not isinstance(body, list):
                raise refusal
            return [_row(raw) for raw in body]
        except (ValueError, KeyError, TypeError) as error:
            raise refusal from error
