"""Tier 2 rows in the comparison, flagged by the rule pack (epic 6 story 4, AC7)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.analysis.toolset import toolset_records, with_toolset
from orchestrator.application.use_cases.metrics_compare import compare_runs
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.test_metric_versions import stored
from tests.unit.application.test_metrics_compare import ENTRIES, World
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.catalogue import FakeCatalogue, catalogue_entry

NOW = datetime(2026, 11, 13, tzinfo=UTC)
LINT = catalogue_entry(id="code.linter_warnings_new", scopes=("run",), additive=False, group="code")
FIRST = catalogue_entry(id="code.test_first_order", scopes=("run",), additive=False, group="code")


def _run(world: World, analyses: FakeAnalysisRepository, pack: str, label: str):  # type: ignore[no-untyped-def]
    run = world.run(label=label)
    records = toolset_records(
        {"gitleaks": "1", "jscpd": "1", "lizard": "1", "osv-scanner": "1"},
        vulnerability_db_date=None,
        lookup_date=None,
        declaration_hash="d",
        extra=({"tool": "opengrep", "version": "1.0", "rule_pack_hash": pack},),
    )
    found = with_toolset(
        Analysis(id=new_id(), run_id=run.id, repository_path=".", status="ok", created_at=NOW),
        records,
    )
    analyses.add(found)
    values = [
        stored("code.linter_warnings_new", scope_type="run", scope_key="run", value_num=Decimal(3)),
        stored("code.test_first_order", scope_type="run", scope_key="run", value_num=Decimal(1)),
    ]
    world.versions.add(
        ResultVersion(
            id=new_id(),
            run_id=run.id,
            n=1,
            calculated_at=NOW,
            entry_point=("manual",),
            methods=(),
            analysis_ids=(found.id,),
            toolset_fingerprint=found.toolset_fingerprint,
        ),
        values,
    )
    return run


def test_a_rule_pack_difference_flags_tier_2_but_never_test_first_order() -> None:
    world = World()
    analyses = FakeAnalysisRepository()
    world.ports = replace(
        world.ports, analyses=analyses, catalogue=FakeCatalogue((*ENTRIES, LINT, FIRST))
    )
    one = _run(world, analyses, "aaaaaaaa11", "one")
    two = _run(world, analyses, "bbbbbbbb22", "two")

    result = compare_runs(world.ports, world.query(one, two))

    by_id = {m.metric_id: m for m in result.metrics}
    lint = by_id["code.linter_warnings_new"]
    assert lint.tool_versions_differ is True
    assert {(t.tool, t.version) for t in lint.toolsets[one.id]} >= {("opengrep rules", "aaaaaaaa")}
    assert by_id["code.test_first_order"].tool_versions_differ is False
    assert by_id["code.test_first_order"].toolsets == {}
