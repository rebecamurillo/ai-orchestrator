"""The toolset record and its fingerprint (epic 5 story 3, AC7)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

from orchestrator.application.analysis.toolset import (
    TOOLS,
    UNKNOWN_VERSION,
    fingerprint,
    toolset_records,
    with_toolset,
)
from orchestrator.domain.entities.analysis import Analysis

VERSIONS = {"gitleaks": "8.30.1", "jscpd": "5.4.3", "lizard": "1.26.0", "osv-scanner": "2.7.1"}


def records(
    versions: dict[str, str] | None = None,
    day: date | None = date(2026, 11, 13),
    declaration_hash: str | None = "abc",
) -> tuple[dict[str, object], ...]:
    return toolset_records(
        VERSIONS if versions is None else versions,
        vulnerability_db_date=day,
        lookup_date=day,
        declaration_hash=declaration_hash,
    )


def test_the_record_lists_the_four_tools_in_order_then_the_dates_and_the_hash() -> None:
    found = records()
    assert TOOLS == ("gitleaks", "jscpd", "lizard", "osv-scanner")
    assert found == (
        {"tool": "gitleaks", "version": "8.30.1"},
        {"tool": "jscpd", "version": "5.4.3"},
        {"tool": "lizard", "version": "1.26.0"},
        {"tool": "osv-scanner", "version": "2.7.1"},
        {
            "vulnerability_db_date": "2026-11-13",
            "lookup_date": "2026-11-13",
            "declaration_hash": "abc",
        },
    )


def test_a_tool_with_no_installed_version_reads_unknown_and_an_absent_lookup_has_no_date() -> None:
    """Operator ruling 2026-11-13: the record holds installed versions, not "not run"."""
    found = toolset_records(
        {"gitleaks": "8.30.1"},
        vulnerability_db_date=None,
        lookup_date=None,
        declaration_hash=None,
    )
    assert [r["version"] for r in found[:4]] == ["8.30.1", *[UNKNOWN_VERSION] * 3]
    assert UNKNOWN_VERSION == "unknown"
    assert found[4] == {
        "vulnerability_db_date": None,
        "lookup_date": None,
        "declaration_hash": None,
    }


def test_toolsets_differing_only_in_the_jscpd_version_have_different_fingerprints() -> None:
    other = records({**VERSIONS, "jscpd": "5.4.4"})
    assert fingerprint(records()) != fingerprint(other)


def test_the_same_toolset_twice_has_the_same_fingerprint() -> None:
    assert fingerprint(records()) == fingerprint(records())


def test_the_same_tools_on_two_dates_have_the_same_fingerprint() -> None:
    """Operator ruling 2026-11-13: the dates sit beside the fingerprint, not in it."""
    assert fingerprint(records(day=date(2026, 11, 13))) == fingerprint(
        records(day=date(2026, 12, 1))
    )
    assert fingerprint(records(day=None)) == fingerprint(records())


def test_another_declaration_has_another_fingerprint() -> None:
    assert fingerprint(records(declaration_hash="abc")) != fingerprint(
        records(declaration_hash="d")
    )


def test_the_fingerprint_is_the_sha256_of_the_hash_and_the_sorted_tool_versions() -> None:
    found = records()
    canonical = json.dumps(
        {
            "declaration_hash": "abc",
            "tools": [{"tool": t, "version": VERSIONS[t]} for t in sorted(VERSIONS)],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert fingerprint(found) == hashlib.sha256(canonical.encode()).hexdigest()
    assert len(fingerprint(found)) == 64
    assert fingerprint(tuple(reversed(found))) == fingerprint(found)
    assert fingerprint([{"tool": "x", "version": "1"}]) == fingerprint(
        [{"tool": "x", "version": "1"}, {"lookup_date": "2026-01-01"}]
    )


def test_with_toolset_sets_both_fields_and_nothing_else() -> None:
    analysis = Analysis(
        id=UUID(int=1),
        run_id=UUID(int=2),
        calculation_id=UUID(int=3),
        repository_path=".",
        status="ok",
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    found = records()
    stamped = with_toolset(analysis, found)
    assert stamped.toolset == found
    assert stamped.toolset_fingerprint == fingerprint(found)
    assert stamped.model_copy(update={"toolset": (), "toolset_fingerprint": ""}) == analysis
