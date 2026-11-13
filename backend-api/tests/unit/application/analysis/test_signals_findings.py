"""The findings join one repository's signals and its toolset (epic 6 story 2)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.findings import BUG, FINDINGS_TOOL, OPENGREP, SECURITY
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.signals import RepositorySignals, collect_signals
from orchestrator.application.analysis.toolset import fingerprint
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.workspace import FakeWorkspace

FOUR_TOOLS_AND_DATES = 5
ROOT = Path("/work/analysis")
ANALYSIS_ID = UUID(int=5)
RELATIVE = f"{ANALYSIS_ID}/root"
NOW = datetime(2026, 11, 13, tzinfo=UTC)
FOUND = json.dumps(
    {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "Opengrep", "rules": [{"id": "r1"}]}},
                "results": [
                    {
                        "ruleId": "r1",
                        "level": "error",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "files/app.py"},
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
)


def prepared(rules: str | None) -> RepositoryInputs:
    analysis = Analysis(
        id=ANALYSIS_ID,
        run_id=UUID(int=1),
        calculation_id=UUID(int=2),
        repository_path=".",
        base="b1",
        head="h1",
        status="ok",
        output="",
        declaration_hash="decl",
        created_at=NOW,
    )
    declaration = replace(DEFAULT_DECLARATION, sast_rules=rules)
    return RepositoryInputs(analysis, ROOT / RELATIVE, declaration, (), False)


def collect(
    rules: str | None, rule_text: str = "rule"
) -> tuple[Analysis, FakeAnalysisTools, RepositorySignals]:
    files = {("h1", "app.py"): "x = 1\n", ("b1", "rules.yaml"): rule_text}
    script = AnalysisScript(
        numstat={("b1", "h1"): (NumstatEntry("app.py", 1, 0, False),)},
        name_status={("b1", "h1"): (NameStatus("A", "app.py", None),)},
    )
    workspace = FakeWorkspace(files={f"{RELATIVE}.sast-head.sarif": FOUND})
    tools = FakeAnalysisTools(
        {OPENGREP: ToolRun(0, "", "", "2.0.0")}, workspace=workspace, root=ROOT
    )
    stamped, signals = collect_signals(
        prepared(rules),
        git=FakeGit(analysis=script, files=files),
        scratch_root=workspace,
        tools=tools,
        lookup=FakePackageLookup(),
        lookups=False,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(900, 999)).__next__,
    )
    return stamped, tools, signals


def test_declared_rules_add_counts_artefacts_version_and_a_toolset_record() -> None:
    stamped, _, signals = collect("rules.yaml")
    counts = {(c.metric_id, c.source): c.value for c in signals.counts}
    assert counts[(SECURITY, "fixed")] == 0
    assert counts[(BUG, "high")] + counts[(SECURITY, "high")] == 1
    tools = {a.tool for a in signals.artifacts}
    assert {OPENGREP, FINDINGS_TOOL} <= tools
    assert signals.tool_versions[OPENGREP] == "2.0.0"
    record = stamped.toolset[4]
    assert record["tool"] == OPENGREP
    assert record["rule_pack_hash"]
    assert "declaration_hash" in stamped.toolset[5]
    assert stamped.toolset_fingerprint == fingerprint(stamped.toolset)


def test_the_fingerprint_follows_the_rule_pack() -> None:
    one, _, _ = collect("rules.yaml", "one")
    two, _, _ = collect("rules.yaml", "two")
    assert one.toolset_fingerprint != two.toolset_fingerprint


def test_without_rules_the_toolset_and_the_version_probes_are_the_four_tools_alone() -> None:
    stamped, tools, signals = collect(None)
    assert [r.get("tool") for r in stamped.toolset[:4]] == [
        "gitleaks",
        "jscpd",
        "lizard",
        "osv-scanner",
    ]
    assert len(stamped.toolset) == FOUR_TOOLS_AND_DATES
    assert tools.version_calls == ["gitleaks", "jscpd", "lizard", "osv-scanner"]
    assert signals.words[SECURITY] == signals.words[BUG] == "n/a — no rules declared"
    assert all(c["tool"] != OPENGREP for c in tools.calls)
