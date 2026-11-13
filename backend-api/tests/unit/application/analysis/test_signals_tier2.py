"""`collect_signals` merges Tier 2 (epic 6 story 1)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from orchestrator.application.analysis.declaration import Declaration
from orchestrator.application.analysis.signals import collect_signals
from orchestrator.application.analysis.tier2 import TIER2_IDS, Tier2Ports
from tests.unit.application.analysis.test_signals_collect import (
    NOW,
    ROOT,
    git,
    prepared,
)
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace

LOG = "00000000-0000-0000-0000-000000000005/root.tier2-logs/{}-lint.log"


def collect(declaration: Declaration, ports: Tier2Ports | None, workspace: FakeWorkspace):  # type: ignore[no-untyped-def]
    inputs = replace(prepared(), declaration=declaration)
    return collect_signals(
        inputs,
        git=git(),
        scratch_root=workspace,
        tools=FakeAnalysisTools(workspace=workspace, root=ROOT),
        lookup=FakePackageLookup(),
        lookups=False,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(900, 999)).__next__,
        tier2=ports,
    )


def test_without_a_declaration_every_tier_2_signal_is_not_declared() -> None:
    _, signals = collect(Declaration(), None, FakeWorkspace())
    assert {i: signals.words[i] for i in TIER2_IDS} == dict.fromkeys(
        TIER2_IDS, "n/a — tier 2 not declared"
    )


def test_tier_2_counts_words_and_artefacts_are_merged() -> None:
    workspace = FakeWorkspace(
        "/work/analysis",
        {LOG.format("base"): "a.py:1:1: x\n", LOG.format("head"): "a.py:1:1: x\na.py:2:1: y\n"},
    )
    runner = FakeProcessRunner()
    declaration = Declaration(tier2=True, commands={"lint": "L"})
    _, signals = collect(declaration, Tier2Ports(runner, 20, {}), workspace)
    lint = [c for c in signals.counts if c.metric_id == "code.linter_warnings_new"]
    assert [c.value for c in lint] == [1]
    assert signals.words["code.typecheck_errors_new"] == "n/a — no typecheck command declared"
    assert {"tier2:base:lint", "tier2:head:lint"} <= {a.tool for a in signals.artifacts}
