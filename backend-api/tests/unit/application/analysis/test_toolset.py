"""The toolset record and its fingerprint (epic 5 story 3, AC7)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

from orchestrator.application.analysis.toolset import (
    NOT_RUN_VERSION,
    TOOLS,
    fingerprint,
    toolset_records,
    with_toolset,
)
from orchestrator.domain.entities.analysis import Analysis

VERSIONS = {"gitleaks": "8.30.1", "jscpd": "5.4.3", "lizard": "1.26.0", "osv-scanner": "2.7.1"}


def records(versions: dict[str, str] | None = None) -> tuple[dict[str, object], ...]:
    return toolset_records(
        VERSIONS if versions is None else versions,
        vulnerability_db_date=date(2026, 11, 13),
        lookup_date=date(2026, 11, 13),
        declaration_hash="abc",
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


def test_a_tool_that_did_not_run_reads_not_run_and_an_absent_lookup_has_no_date() -> None:
    found = toolset_records(
        {"gitleaks": "8.30.1"},
        vulnerability_db_date=None,
        lookup_date=None,
        declaration_hash=None,
    )
    assert [r["version"] for r in found[:4]] == [
        "8.30.1",
        NOT_RUN_VERSION,
        NOT_RUN_VERSION,
        NOT_RUN_VERSION,
    ]
    assert NOT_RUN_VERSION == "not run"
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


def test_the_fingerprint_is_the_sha256_of_the_canonical_json() -> None:
    found = records()
    canonical = json.dumps(list(found), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert fingerprint(found) == hashlib.sha256(canonical.encode()).hexdigest()
    assert len(fingerprint(found)) == 64
    assert fingerprint([{"b": 1, "a": 2}]) == fingerprint([{"a": 2, "b": 1}])


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
