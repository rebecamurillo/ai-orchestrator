"""The opengrep rule pack as a compared tool (epic 6 story 4, AC7)."""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.application.metrics.compare_toolsets import (
    DECLARATION_TOOL,
    NO_TOOLSET_METRICS,
    RULE_PACK_TOOL,
    run_toolset,
)
from orchestrator.application.metrics.compare_views import ToolVersion
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ids import new_id


def _analysis(*records: dict[str, object]) -> Analysis:
    return Analysis(
        id=new_id(),
        run_id=new_id(),
        repository_path=".",
        status="ok",
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
        toolset=records,
        declaration_hash="decl",
    )


def _opengrep(pack: str | None) -> dict[str, object]:
    return {"tool": "opengrep", "version": "1.0", "rule_pack_hash": pack}


def test_a_rule_pack_hash_is_a_tool_of_its_own() -> None:
    toolset = run_toolset([_analysis(_opengrep("abcdef1234567890"))])

    assert ToolVersion(RULE_PACK_TOOL, "abcdef12") in toolset
    assert RULE_PACK_TOOL == "opengrep rules"
    assert toolset[-1].tool == DECLARATION_TOOL


def test_an_absent_hash_reads_none_and_two_hashes_are_joined() -> None:
    assert ToolVersion(RULE_PACK_TOOL, "none") in run_toolset([_analysis(_opengrep(None))])
    both = run_toolset([_analysis(_opengrep("bbbbbbbb11")), _analysis(_opengrep("aaaaaaaa22"))])
    assert ToolVersion(RULE_PACK_TOOL, "aaaaaaaa/bbbbbbbb") in both


def test_without_an_opengrep_record_the_list_is_unchanged() -> None:
    toolset = run_toolset([_analysis({"tool": "jscpd", "version": "4"})])

    assert [t.tool for t in toolset] == ["jscpd", DECLARATION_TOOL]


def test_test_first_order_is_read_from_logs_not_by_a_tool() -> None:
    assert NO_TOOLSET_METRICS == ("code.test_first_order",)
