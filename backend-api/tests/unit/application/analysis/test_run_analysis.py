"""`analyse_run`: every repository of a Run analysed, stored pending or under a calculation
(epic 5 story 4, AC2, AC4, AC5)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.run_analysis import (
    AnalysisDeps,
    AnalysisScope,
    analyse_run,
    load_code,
    pending_analyses,
)
from orchestrator.application.analysis.signals import SUMMARY_TOOL, signals_from_json
from orchestrator.application.templates.step_metric_model import StepMetric
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.catalogue import CatalogueEntry, CatalogueMethod
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.run_records import FakeRunCommitRepository, FakeRunRepositoryRecords
from tests.unit.fakes.runs import FakeAttemptRepository, FakeStepRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

RUN = UUID(int=1)
CALCULATION = UUID(int=2)
WORK = Path("/work")
NOW = datetime(2026, 11, 13, tzinfo=UTC)
TWO = 2


def record(path: str, n: int, head: str | None = "h1") -> RunRepositoryRecord:
    return RunRepositoryRecord(
        id=UUID(int=n),
        run_id=RUN,
        path=path,
        remote_url=f"https://example.invalid/{n}.git",
        base_branch="main",
        head_pushed=head,
    )


class Ids:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> UUID:
        self.count += 1
        return UUID(int=1000 + self.count)


class World:
    def __init__(self, records: Sequence[RunRepositoryRecord], git: FakeGit | None = None) -> None:
        self.analyses = FakeAnalysisRepository()
        self.records = FakeRunRepositoryRecords()
        for item in records:
            self.records.add(item)
        self.commits = FakeRunCommitRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.units: list[FakeUnitOfWork] = []
        self.scratch = FakeWorkspace()
        self.git = git or FakeGit(
            analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"})
        )
        self.tools = FakeAnalysisTools()

    @contextmanager
    def writes(self) -> Iterator[AnalysisScope]:
        unit = FakeUnitOfWork()
        self.units.append(unit)
        with unit:
            yield AnalysisScope(
                steps=self.steps,
                attempts=self.attempts,
                run_records=self.records,
                run_commits=self.commits,
                analyses=self.analyses,
                uow=unit,
            )

    def deps(self, tools: FakeAnalysisTools | None = None) -> AnalysisDeps:
        return AnalysisDeps(
            git=self.git,
            tools=tools or self.tools,
            lookup=FakePackageLookup(),
            lookups=False,
            scratch_root=self.scratch,
            work_dir=WORK,
            clock=FakeClock(NOW),
            new_id=Ids(),
        )

    def open_units(self) -> int:
        return sum(1 for unit in self.units if unit.is_open)


def test_each_repository_is_stored_pending_with_its_summary() -> None:  # AC2
    world = World([record(".", 10), record("repos/x", 11)])

    analyses = analyse_run(world.deps(), world.writes, RUN, None)

    assert len(analyses) == TWO
    assert {a.repository_path for a in world.analyses.rows} == {".", "repos/x"}
    assert all(a.calculation_id is None for a in world.analyses.rows)
    assert all(world.analyses.artifact(a.id, SUMMARY_TOOL) is not None for a in analyses)
    assert all(
        world.analyses.artifact(a.id, SUMMARY_TOOL).media_type == "application/json"  # type: ignore[union-attr]
        for a in analyses
    )
    assert all(unit.committed for unit in world.units if unit.calls.count("commit"))


def test_the_calculation_id_is_stamped_on_every_analysis() -> None:  # AC5
    world = World([record(".", 10)])

    analyse_run(world.deps(), world.writes, RUN, CALCULATION)

    assert [a.calculation_id for a in world.analyses.rows] == [CALCULATION]
    assert world.analyses.list_for_calculation(CALCULATION) == world.analyses.rows


def test_a_repository_without_a_pushed_head_is_a_failed_analysis_and_the_next_is_read() -> None:
    world = World([record("repos/x", 11, head=None), record(".", 10)])

    analyses = analyse_run(world.deps(), world.writes, RUN, None)

    assert {a.repository_path: a.status for a in analyses} == {"repos/x": "failed", ".": "ok"}
    assert len(world.analyses.rows) == TWO


class BrokenTools(FakeAnalysisTools):
    def version(self, tool: str) -> str:
        raise RuntimeError("boom\nsecond line")


def test_an_error_while_reading_one_repository_fails_every_analysis_it_touches_not_the_run() -> (
    None
):
    world = World([record(".", 10), record("repos/y", 12, head=None)])

    analyses = analyse_run(world.deps(BrokenTools()), world.writes, RUN, None)

    by_path = {a.repository_path: a for a in analyses}
    assert by_path["."].status == "failed"
    assert by_path["."].output == "RuntimeError: boom"
    assert by_path["repos/y"].status == "failed"
    assert len(world.analyses.rows) == TWO
    assert all(world.analyses.artifact(a.id, SUMMARY_TOOL) for a in analyses)


class WatchingTools(FakeAnalysisTools):
    def __init__(self, world: World) -> None:
        super().__init__({"gitleaks": ToolRun(0, "", "", "8.30.1")})
        self.world = world
        self.open_during_runs: list[int] = []

    def run(self, tool, args, cwd, timeout):  # type: ignore[no-untyped-def]
        self.open_during_runs.append(self.world.open_units())
        return super().run(tool, args, cwd, timeout)


def test_no_unit_of_work_is_open_while_a_tool_runs() -> None:
    diff = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1,2 @@\n-x\n+const a = 1;\n"
    script = AnalysisScript(
        merge_bases={("h1", "origin/main"): "m0"},
        numstat={("m0", "h1"): (NumstatEntry("a", 1, 1, False),)},
        name_status={("m0", "h1"): (NameStatus("M", "a", None),)},
        diff_text={("m0", "h1"): diff},
    )
    world = World([record(".", 10)], FakeGit(analysis=script))
    tools = WatchingTools(world)

    analyse_run(world.deps(tools), world.writes, RUN, None)

    assert tools.open_during_runs
    assert set(tools.open_during_runs) == {0}


def test_the_scratch_folders_are_removed() -> None:
    world = World([record(".", 10)])
    leftover = f"{UUID(int=1001)}/root/file"
    world.scratch.write(leftover, "x")

    analyse_run(world.deps(), world.writes, RUN, None)

    assert not world.scratch.exists(leftover)


def test_attempt_ranges_and_known_paths_come_from_the_runs_rows() -> None:
    world = World([record(".", 10)])
    world.steps.add_many([step_row()])

    analyse_run(world.deps(), world.writes, RUN, None)

    assert world.analyses.rows[0].status == "ok"


def step_row() -> StepRun:
    return StepRun(
        id=UUID(int=500),
        run_id=RUN,
        seq=1,
        path="steps[0]",
        label="a",
        kind="shell",
        gate="unvalidated",
        status="done",
    )


def analysis(
    path: str, n: int, minutes: int, calculation: UUID | None, run: UUID = RUN
) -> Analysis:
    return Analysis(
        id=UUID(int=n),
        run_id=run,
        calculation_id=calculation,
        repository_path=path,
        status="ok",
        created_at=NOW + timedelta(minutes=minutes),
    )


def test_pending_analyses_are_the_newest_per_path_without_a_calculation() -> None:
    old = analysis(".", 1, 0, None)
    new = analysis(".", 2, 5, None)
    member = analysis("repos/x", 3, 1, None)
    taken = analysis(".", 4, 9, CALCULATION)
    foreign = analysis(".", 5, 9, None, run=UUID(int=9))

    found = pending_analyses([old, new, member, taken, foreign], RUN)

    assert found == [new, member]
    assert pending_analyses([new, old], RUN) == [new]
    assert pending_analyses([], RUN) == []


def test_load_code_reads_the_summary_back_and_a_missing_summary_is_failed() -> None:
    world = World([record(".", 10)])
    done = analyse_run(world.deps(), world.writes, RUN, None)
    bare = analysis("repos/z", 77, 0, None)

    code = load_code(world.analyses, [*done, bare])

    assert [signals.path for signals in code] == [".", "repos/z"]
    assert code[0].status == "ok"
    assert code[1].status == "failed"
    assert "summary" in code[1].output


def test_the_runs_declared_step_metrics_reach_its_own_repositorys_signals() -> None:
    entry = CatalogueEntry(
        "step.bench-v1.heldout_tests",
        "held-out",
        "step",
        "A",
        ("run",),
        "tests",
        "report",
        None,
        False,
        (),
        None,
        False,
        (CatalogueMethod(1, "reads it", {}),),
    )
    declared = StepMetric(line=1, entry=entry, format="junit", path="out/heldout.xml")
    asked: list[UUID] = []

    def step_metrics(run_id: UUID) -> Sequence[StepMetric]:
        asked.append(run_id)
        return [declared]

    git = FakeGit(
        analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}),
        files={
            ("h1", "out/heldout.xml"): '<testsuite><testcase classname="c" name="a"/></testsuite>'
        },
        listings={("h1", "out"): ["out/heldout.xml"]},
    )
    world = World([record(".", 10)], git)

    [stored] = analyse_run(
        replace(world.deps(), step_metrics=step_metrics), world.writes, RUN, None
    )

    assert asked == [RUN]
    signals = signals_from_json(world.analyses.artifact(stored.id, SUMMARY_TOOL).body)  # type: ignore[union-attr]
    assert {c.source: c.value for c in signals.counts if c.metric_id == entry.id}["passed"] == 1
