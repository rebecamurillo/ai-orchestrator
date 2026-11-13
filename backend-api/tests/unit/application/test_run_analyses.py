"""The read of a Run's analyses for the METRICS tab (epic 5 story 5, AC1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from orchestrator.application.analysis.signals import (
    SUMMARY_TOOL,
    RepositorySignals,
    signals_to_json,
)
from orchestrator.application.analysis.toolset import toolset_records, with_toolset
from orchestrator.application.use_cases.analysis_sarif import SARIF_MEDIA_TYPE
from orchestrator.application.use_cases.run_analyses import RunAnalysesPorts, run_analyses
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.test_metrics_spend import a_project, a_run
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.metric_results import FakeResultVersionRepository
from tests.unit.fakes.run_records import FakeRunRepositoryRecords
from tests.unit.fakes.runs import FakeRunRepository

TWO = 2
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class World:
    def __init__(self) -> None:
        self.run = a_run(a_project("familio"))
        self.runs = FakeRunRepository()
        self.runs.add(self.run)
        self.versions = FakeResultVersionRepository()
        self.analyses = FakeAnalysisRepository()
        self.records = FakeRunRepositoryRecords()
        self.ports = RunAnalysesPorts(self.runs, self.versions, self.analyses, self.records)

    def analysis(self, path: str, *, status: str = "ok", output: str = "") -> Analysis:
        records = toolset_records(
            {"gitleaks": "8.30.1", "jscpd": "4.0.5", "lizard": "1.17", "osv-scanner": "2.0"},
            vulnerability_db_date=date(2026, 11, 12),
            lookup_date=date(2026, 11, 13),
            declaration_hash="decl",
        )
        found = with_toolset(
            Analysis(
                id=new_id(),
                run_id=self.run.id,
                repository_path=path,
                base="b" * 40,
                head="h" * 40,
                status=status,  # type: ignore[arg-type]
                output=output,
                created_at=NOW,
            ),
            records,
        )
        self.analyses.add(found)
        return found

    def summary(self, found: Analysis, **over: object) -> None:
        signals = RepositorySignals(found.repository_path, found.status, "", (), **over)  # type: ignore[arg-type]
        self.analyses.add_artifact(
            AnalysisArtifact(
                id=new_id(),
                analysis_id=found.id,
                tool=SUMMARY_TOOL,
                media_type="application/json",
                body=signals_to_json(signals),
            )
        )

    def sarif(self, found: Analysis, tool: str, media: str = SARIF_MEDIA_TYPE) -> None:
        self.analyses.add_artifact(
            AnalysisArtifact(
                id=new_id(), analysis_id=found.id, tool=tool, media_type=media, body=b"{}"
            )
        )

    def record(self, path: str, base_branch: str) -> None:
        self.records.add(
            RunRepositoryRecord(
                id=new_id(),
                run_id=self.run.id,
                path=path,
                remote_url="u",
                base_branch=base_branch,
            )
        )

    def version(self, n: int, *analyses: Analysis) -> None:
        self.versions.add(
            ResultVersion(
                id=new_id(),
                run_id=self.run.id,
                n=n,
                calculated_at=NOW,
                entry_point=("manual",),
                methods=(),
                analysis_ids=tuple(a.id for a in analyses),
            ),
            [],
        )


def test_two_analyses_come_root_first_with_their_detail() -> None:
    world = World()
    app = world.analysis("repos/app")
    root = world.analysis(".")
    world.summary(root, languages=("Python",), commits_not_made_by_run=())
    world.summary(app, languages=("TypeScript", "CSS"), commits_not_made_by_run=("a", "b"))
    world.record(".", "main")
    world.record("repos/app", "develop")
    world.sarif(root, "gitleaks")
    world.sarif(root, "jscpd", "application/json")
    world.version(1, app, root)

    result = run_analyses(world.ports, world.run.id, None)

    assert result.version == 1
    first, second = result.items
    assert [first.repository_path, second.repository_path] == [".", "repos/app"]
    assert first.base_branch == "main"
    assert second.base_branch == "develop"
    assert first.base == "b" * 40
    assert first.languages == ["Python"]
    assert first.commits_outside_run == 0
    assert second.commits_outside_run == TWO
    assert first.sarif_tools == ["gitleaks"]
    assert second.sarif_tools == []
    assert [t.tool for t in first.tools] == ["gitleaks", "jscpd", "lizard", "osv-scanner"]
    assert first.vulnerability_db_date == date(2026, 11, 12)
    assert first.lookup_date == date(2026, 11, 13)
    assert first.declaration_hash == "decl"
    assert first.reason == ""


def test_a_missing_summary_and_an_unknown_record_leave_none() -> None:
    world = World()
    failed = world.analysis(".", status="failed", output="commit missing: abc\nboom")
    world.version(1, failed)

    [item] = run_analyses(world.ports, world.run.id, 1).items

    assert item.languages is None
    assert item.commits_outside_run is None
    assert item.base_branch is None
    assert item.reason == "commit missing: abc"
    assert item.status == "failed"


def test_a_summary_stored_before_the_story_holds_none() -> None:
    world = World()
    found = world.analysis(".")
    world.summary(found)
    world.version(1, found)

    [item] = run_analyses(world.ports, world.run.id, 1).items

    assert item.languages is None
    assert item.commits_outside_run is None


def test_no_version_is_an_empty_answer() -> None:
    world = World()

    result = run_analyses(world.ports, world.run.id, None)

    assert (result.version, result.items) == (None, [])


def test_the_newest_version_is_read_when_none_is_named() -> None:
    world = World()
    found = world.analysis(".")
    world.version(1)
    world.version(2, found)

    assert run_analyses(world.ports, world.run.id, None).version == TWO
    assert run_analyses(world.ports, world.run.id, 1).items == []


@pytest.mark.parametrize("run, v", [(UUID(int=9), None), (None, 7)], ids=["run", "version"])
def test_an_unknown_run_or_version_is_not_found(run: UUID | None, v: int | None) -> None:
    world = World()

    with pytest.raises(NotFound):
        run_analyses(replace(world.ports), run or world.run.id, v)
