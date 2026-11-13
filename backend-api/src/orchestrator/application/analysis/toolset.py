"""The toolset an analysis ran with, and its fingerprint (ARCHITECTURE §7.5).

Two analyses are comparable only when measured the same way. The fingerprint is the SHA-256 of
the canonical JSON of the declaration hash and the sorted `{tool, installed version}` of every
Tier 1 tool, whether or not it ran; the lookup and vulnerability-database dates are stored
beside it and are not part of it (Operator ruling 2026-11-13).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from orchestrator.domain.entities.analysis import Analysis

TOOLS = ("gitleaks", "jscpd", "lizard", "osv-scanner")
UNKNOWN_VERSION = "unknown"
DECLARATION_HASH = "declaration_hash"


def toolset_records(
    installed: Mapping[str, str],
    *,
    vulnerability_db_date: date | None,
    lookup_date: date | None,
    declaration_hash: str | None,
) -> tuple[dict[str, Any], ...]:
    """`{tool, installed version}` per tool, then the dates and the declaration hash."""
    return (
        *({"tool": tool, "version": installed.get(tool, UNKNOWN_VERSION)} for tool in TOOLS),
        {
            "vulnerability_db_date": vulnerability_db_date.isoformat()
            if vulnerability_db_date is not None
            else None,
            "lookup_date": lookup_date.isoformat() if lookup_date is not None else None,
            DECLARATION_HASH: declaration_hash,
        },
    )


def fingerprint(records: Sequence[Mapping[str, Any]]) -> str:
    tools = sorted(
        ({"tool": r["tool"], "version": r["version"]} for r in records if "tool" in r),
        key=lambda r: (r["tool"], r["version"]),
    )
    hashes = [r[DECLARATION_HASH] for r in records if DECLARATION_HASH in r]
    canonical = json.dumps(
        {DECLARATION_HASH: hashes[0] if hashes else None, "tools": tools},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def with_toolset(analysis: Analysis, records: tuple[dict[str, Any], ...]) -> Analysis:
    return analysis.model_copy(
        update={"toolset": records, "toolset_fingerprint": fingerprint(records)}
    )
