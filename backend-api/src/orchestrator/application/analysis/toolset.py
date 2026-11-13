"""The toolset an analysis ran with, and its fingerprint (ARCHITECTURE §7.5).

Two analyses are comparable only when measured the same way: the fingerprint is the SHA-256 of
the toolset's canonical JSON, tools in fixed order and keys sorted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from orchestrator.domain.entities.analysis import Analysis

TOOLS = ("gitleaks", "jscpd", "lizard", "osv-scanner")
NOT_RUN_VERSION = "not run"


def toolset_records(
    tool_versions: Mapping[str, str],
    *,
    vulnerability_db_date: date | None,
    lookup_date: date | None,
    declaration_hash: str | None,
) -> tuple[dict[str, Any], ...]:
    """`{tool, version}` per tool, then the dates and the declaration hash."""
    return (
        *({"tool": tool, "version": tool_versions.get(tool, NOT_RUN_VERSION)} for tool in TOOLS),
        {
            "vulnerability_db_date": vulnerability_db_date.isoformat()
            if vulnerability_db_date is not None
            else None,
            "lookup_date": lookup_date.isoformat() if lookup_date is not None else None,
            "declaration_hash": declaration_hash,
        },
    )


def fingerprint(records: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(records), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def with_toolset(analysis: Analysis, records: tuple[dict[str, Any], ...]) -> Analysis:
    return analysis.model_copy(
        update={"toolset": records, "toolset_fingerprint": fingerprint(records)}
    )
