"""`collect_signals` with step metrics: Tier 3 merged like the other tiers (epic 6 story 3)."""

from __future__ import annotations

import json

from orchestrator.application.analysis.signals import (
    RepositorySignals,
    collect_signals,
    signals_from_json,
    signals_to_json,
)
from orchestrator.application.templates.step_metric_model import StepMetric
from orchestrator.domain.ports.catalogue import CatalogueEntry, CatalogueMethod
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.application.analysis.test_signals_collect import NOW, prepared
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.workspace import FakeWorkspace

ID = "step.bench-v1.heldout_tests"
REPORT = (
    '<testsuite><testcase classname="c" name="a"/>'
    '<testcase classname="c" name="b"><failure message="x"/></testcase></testsuite>'
)
STRAY = '<testsuite><testcase classname="c" name="a"/></testsuite>'


def declared() -> StepMetric:
    entry = CatalogueEntry(
        ID,
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
    return StepMetric(line=1, entry=entry, format="junit", path="out/heldout.xml")


def git() -> FakeGit:
    paths = ("out/heldout.xml", "out/other.xml")
    script = AnalysisScript(
        numstat={("b1", "h1"): tuple(NumstatEntry(p, 1, 0, False) for p in paths)},
        name_status={("b1", "h1"): tuple(NameStatus("A", p, None) for p in paths)},
    )
    return FakeGit(
        analysis=script,
        files={("h1", "out/heldout.xml"): REPORT, ("h1", "out/other.xml"): STRAY},
        listings={("h1", "out"): list(paths)},
    )


def collect(step_metrics: list[StepMetric] | None) -> RepositorySignals:
    workspace = FakeWorkspace()
    kwargs = {} if step_metrics is None else {"step_metrics": step_metrics}
    _, signals = collect_signals(
        prepared(),
        git=git(),
        scratch_root=workspace,
        tools=FakeAnalysisTools(workspace=workspace),
        lookup=FakePackageLookup(),
        lookups=False,
        now=NOW,
        new_id=iter(__import__("uuid").UUID(int=n) for n in range(900, 999)).__next__,
        **kwargs,  # type: ignore[arg-type]
    )
    return signals


def test_declared_counts_merge_with_the_other_tiers_and_the_stray_file_is_listed() -> None:
    signals = collect([declared()])

    mine = {c.source: c.value for c in signals.counts if c.metric_id == ID}
    assert mine == {"passed": 1, "failed": 1, "errored": 0, "skipped": 0}
    assert any(c.metric_id == "code.lines_added" for c in signals.counts)
    assert signals.not_catalogued == ("out/other.xml",)


def test_with_no_declaration_every_report_is_undeclared() -> None:
    signals = collect(None)

    assert not any(c.metric_id.startswith("step.") for c in signals.counts)
    assert signals.not_catalogued == ("out/heldout.xml", "out/other.xml")


def test_not_catalogued_survives_a_json_round_trip() -> None:
    signals = collect([declared()])

    assert signals_from_json(signals_to_json(signals)).not_catalogued == ("out/other.xml",)


def test_a_summary_stored_before_the_key_existed_loads_with_none() -> None:
    document = json.loads(signals_to_json(collect([declared()])))
    del document["not_catalogued"]

    assert signals_from_json(json.dumps(document).encode()).not_catalogued == ()
