"""Static signals in the comparison (epic 5 story 5: AC6, AC7, AC8)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.analysis.toolset import toolset_records, with_toolset
from orchestrator.application.metrics.compare_views import ToolVersion
from orchestrator.application.use_cases.metrics_compare import compare_runs
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.application.test_metric_versions import stored
from tests.unit.application.test_metrics_compare import ENTRIES, World, run_value
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.catalogue import FakeCatalogue, catalogue_entry

NOW = datetime(2026, 11, 13, tzinfo=UTC)
CODE = catalogue_entry(id="code.duplication_added", scopes=("run",), additive=False, group="code")


def _world() -> tuple[World, FakeAnalysisRepository]:
    world = World()
    analyses = FakeAnalysisRepository()
    world.ports = replace(world.ports, analyses=analyses, catalogue=FakeCatalogue((*ENTRIES, CODE)))
    return world, analyses


def _analysed(world: World, analyses: FakeAnalysisRepository, jscpd: str | None, label: str) -> Run:
    run = world.run(label=label)
    values = [
        stored(
            "code.duplication_added",
            scope_type="run",
            scope_key="run",
            value_num=Decimal(7),
        ),
        run_value("tokens.input", "1"),
    ]
    ids: list[UUID] = []
    fingerprint: str | None = None
    if jscpd is not None:
        records = toolset_records(
            {"gitleaks": "1", "jscpd": jscpd, "lizard": "1", "osv-scanner": "1"},
            vulnerability_db_date=None,
            lookup_date=None,
            declaration_hash="d",
        )
        found = with_toolset(
            Analysis(id=new_id(), run_id=run.id, repository_path=".", status="ok", created_at=NOW),
            records,
        )
        analyses.add(found)
        ids = [found.id]
        fingerprint = found.toolset_fingerprint
        values += [
            stored("code.lines_added", scope_type="run", scope_key="run", value_num=Decimal(40)),
            stored("code.lines_removed", scope_type="run", scope_key="run", value_num=Decimal(2)),
            stored("code.files_touched", scope_type="run", scope_key="run", value_num=Decimal(3)),
        ]
    world.versions.add(
        ResultVersion(
            id=new_id(),
            run_id=run.id,
            n=1,
            calculated_at=NOW,
            entry_point=("manual",),
            methods=(),
            analysis_ids=tuple(ids),
            toolset_fingerprint=fingerprint,
        ),
        values,
    )
    return run


def _code(comparison):  # type: ignore[no-untyped-def]
    return next(m for m in comparison.metrics if m.metric_id == "code.duplication_added")


def test_differing_fingerprints_flag_every_code_row_with_both_toolsets() -> None:
    world, analyses = _world()
    one = _analysed(world, analyses, "4.0.5", "one")
    two = _analysed(world, analyses, "4.1.0", "two")

    comparison = compare_runs(world.ports, world.query(one, two))

    metric = _code(comparison)
    assert metric.tool_versions_differ is True
    assert ToolVersion("jscpd", "4.0.5") in metric.toolsets[one.id]
    assert ToolVersion("jscpd", "4.1.0") in metric.toolsets[two.id]
    other = next(m for m in comparison.metrics if m.metric_id == "tokens.input")
    assert other.tool_versions_differ is False
    assert other.toolsets == {}


def test_one_shared_fingerprint_flags_nothing() -> None:
    world, analyses = _world()
    one = _analysed(world, analyses, "4.0.5", "one")
    two = _analysed(world, analyses, "4.0.5", "two")

    metric = _code(compare_runs(world.ports, world.query(one, two)))

    assert metric.tool_versions_differ is False
    assert metric.toolsets == {}


def test_diff_size_is_sized_for_an_analysed_run_and_not_run_for_the_other() -> None:
    world, analyses = _world()
    one = _analysed(world, analyses, None, "one")
    two = _analysed(world, analyses, "4.0.5", "two")

    comparison = compare_runs(world.ports, world.query(one, two))

    assert comparison.diff_size[one.id] == "not run"
    assert comparison.diff_size[two.id] == "+40 \N{MINUS SIGN}2 · 3 files"
    assert _code(comparison).tool_versions_differ is False


def test_a_world_without_an_analysis_port_reads_not_run() -> None:
    world = World()
    one = world.run(label="one")
    two = world.run(label="two")
    world.version(one, 1, [run_value("tokens.input", "1")])
    world.version(two, 1, [run_value("tokens.input", "1")])

    comparison = compare_runs(world.ports, world.query(one, two))

    assert set(comparison.diff_size.values()) == {"not run"}
