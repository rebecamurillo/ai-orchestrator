"""Extra tool records join the toolset before the dates and move its fingerprint (epic 6 s2)."""

from __future__ import annotations

from datetime import date

from orchestrator.application.analysis.toolset import fingerprint, toolset_records

TOOLS_EXTRA_AND_DATES = 6
DISTINCT = 3
VERSIONS = {"gitleaks": "8.30.1", "jscpd": "5.4.3", "lizard": "1.26.0", "osv-scanner": "2.7.1"}


def records(*extra: dict[str, object]) -> tuple[dict[str, object], ...]:
    return toolset_records(
        VERSIONS,
        vulnerability_db_date=date(2026, 11, 13),
        lookup_date=None,
        declaration_hash="abc",
        extra=extra,
    )


def test_an_extra_record_sits_after_the_four_tools_and_before_the_dates() -> None:
    opengrep = {"tool": "opengrep", "version": "2.0.0", "rule_pack_hash": "h1"}
    found = records(opengrep)
    assert found[4] == opengrep
    assert "declaration_hash" in found[5]
    assert len(found) == TOOLS_EXTRA_AND_DATES


def test_no_extra_leaves_the_record_as_it_was() -> None:
    assert records() == toolset_records(
        VERSIONS, vulnerability_db_date=date(2026, 11, 13), lookup_date=None, declaration_hash="abc"
    )


def test_the_rule_pack_hash_moves_the_fingerprint() -> None:
    one = fingerprint(records({"tool": "opengrep", "version": "2.0.0", "rule_pack_hash": "h1"}))
    two = fingerprint(records({"tool": "opengrep", "version": "2.0.0", "rule_pack_hash": "h2"}))
    none = fingerprint(records({"tool": "opengrep", "version": "2.0.0", "rule_pack_hash": None}))
    assert len({one, two, none}) == DISTINCT


def test_a_record_without_a_hash_fingerprints_as_before() -> None:
    plain = fingerprint(records())
    versioned = fingerprint(records({"tool": "opengrep", "version": "2.0.0"}))
    assert plain != versioned
    assert versioned == fingerprint(records({"tool": "opengrep", "version": "2.0.0"}))
