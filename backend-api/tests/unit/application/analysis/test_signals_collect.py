"""One call per repository: Tier 1a and 1b together, with the toolset (epic 5 story 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.signals import RepositorySignals, collect_signals
from orchestrator.application.analysis.summary import summarise
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.toolset import fingerprint
from orchestrator.application.metrics.values import value_at
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.workspace import FakeWorkspace

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis"
ROOT = Path("/work/analysis")
ANALYSIS_ID = UUID(int=5)
NOW = datetime(2026, 11, 13, tzinfo=UTC)
LOCK = (FIXTURES / "tier1b" / "pnpm-lock.head.yaml").read_text()


def analysis(status: str = "ok", declaration_hash: str | None = "decl") -> Analysis:
    return Analysis(
        id=ANALYSIS_ID,
        run_id=UUID(int=1),
        calculation_id=UUID(int=2),
        repository_path=".",
        base="b1",
        head="h1",
        status=status,  # type: ignore[arg-type]
        output="boom" if status == "failed" else "",
        declaration_hash=declaration_hash,
        created_at=NOW,
    )


def prepared(status: str = "ok") -> RepositoryInputs:
    scratch = None if status == "failed" else ROOT / f"{ANALYSIS_ID}/root"
    return RepositoryInputs(analysis(status), scratch, DEFAULT_DECLARATION, (), False)


def git() -> FakeGit:
    script = AnalysisScript(
        numstat={("b1", "h1"): (NumstatEntry("pnpm-lock.yaml", 4, 0, False),)},
        name_status={("b1", "h1"): (NameStatus("M", "pnpm-lock.yaml", None),)},
    )
    return FakeGit(analysis=script, files={("h1", "pnpm-lock.yaml"): LOCK})


def collect(
    fake_tools: FakeAnalysisTools,
    workspace: FakeWorkspace,
    lookup: FakePackageLookup,
    status: str = "ok",
    *,
    lookups: bool = True,
) -> tuple[Analysis, RepositorySignals]:
    return collect_signals(
        prepared(status),
        git=git(),
        scratch_root=workspace,
        tools=fake_tools,
        lookup=lookup,
        lookups=lookups,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(900, 999)).__next__,
    )


def test_both_tiers_are_collected_and_the_analysis_carries_the_toolset() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {"jscpd": ToolRun(0, "", "", "5.4.3"), "lizard": ToolRun(0, "", "", "1.26.0")},
        workspace=workspace,
        root=ROOT,
    )
    stamped, signals = collect(tools, workspace, FakePackageLookup())
    ids = {c.metric_id for c in signals.counts}
    assert {"code.lines_added", "code.deps_changed", "code.duplication_added"} <= ids
    assert "code.functions_over_cyclomatic" in ids
    assert signals.words["code.functions_over_cognitive"] == "n/a — language not covered"
    assert signals.path == "."
    assert signals.status == "ok"
    versions = {r["tool"]: r["version"] for r in stamped.toolset if "tool" in r}
    assert versions == {
        "gitleaks": "not run",
        "jscpd": "not run",
        "lizard": "1.26.0",
        "osv-scanner": "0.0.0",
    }
    assert stamped.toolset[-1] == {
        "vulnerability_db_date": "2026-11-13",
        "lookup_date": "2026-11-13",
        "declaration_hash": "decl",
    }
    assert stamped.toolset_fingerprint == fingerprint(stamped.toolset)
    assert signals.tool_versions["lizard"] == "1.26.0"
    assert stamped.id == ANALYSIS_ID


def test_a_failed_input_calls_no_tool_and_no_lookup_and_holds_the_empty_toolset() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(workspace=workspace, root=ROOT)
    lookup = FakePackageLookup()
    stamped, signals = collect(tools, workspace, lookup, "failed")
    assert tools.calls == []
    assert lookup.calls == []
    assert signals.status == "failed"
    assert signals.counts == ()
    assert [r.get("version") for r in stamped.toolset[:4]] == ["not run"] * 4
    assert stamped.toolset[-1] == {
        "vulnerability_db_date": None,
        "lookup_date": None,
        "declaration_hash": "decl",
    }
    assert stamped.toolset_fingerprint == fingerprint(stamped.toolset)


def test_lookups_off_is_a_toolset_without_lookup_dates() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(workspace=workspace, root=ROOT)
    lookup = FakePackageLookup()
    stamped, signals = collect(tools, workspace, lookup, lookups=False)
    assert lookup.calls == []
    assert signals.words["code.deps_recent"] == "not run — lookups off"
    assert stamped.toolset[-1]["lookup_date"] is None


def test_the_summary_turns_the_tier_1b_signals_into_values_at_both_scopes() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(workspace=workspace, root=ROOT)
    _, signals = collect(tools, workspace, FakePackageLookup(), lookups=False)
    first = RepositorySignals(
        "web",
        "ok",
        "",
        (
            Count("code.lines_added", "production", 300, None),
            Count("code.duplication_added", None, 4, "production"),
            Count("code.functions_over_cyclomatic", "count", 1, None, "sum"),
            Count("code.functions_over_cyclomatic", "worst", 22, None, "max"),
            Count("code.deps_changed", "added", 2, "production"),
        ),
        {"code.deps_recent": "not run — lookups off"},
    )
    second = RepositorySignals(
        "api",
        "ok",
        "",
        (
            Count("code.lines_added", "production", 100, None),
            Count("code.duplication_added", None, 1, "production"),
            Count("code.functions_over_cyclomatic", "count", 2, None, "sum"),
            Count("code.functions_over_cyclomatic", "worst", 30, None, "max"),
            Count("code.deps_changed", "added", 1, "production"),
        ),
        {"code.deps_recent": "not run — lookups off"},
    )
    values = summarise([first, second])
    assert (
        value_at(values, "code.functions_over_cyclomatic", "repository", "web", "count").value_num
        == 1
    )
    assert value_at(values, "code.functions_over_cyclomatic", "run", "run", "count").value_num == 3
    assert value_at(values, "code.functions_over_cyclomatic", "run", "run", "worst").value_num == 30
    assert value_at(values, "code.duplication_added", "run", "run").value_num == 5
    assert (
        value_at(values, "code.duplication_added", "repository", "api", "small_change").missing
        == "small change"
    )
    assert value_at(values, "code.deps_changed", "run", "run", "added").value_num == 3
    word = value_at(values, "code.deps_recent", "run", "run")
    assert word.value_num is None
    assert word.missing == "not run — lookups off"
    assert (
        value_at(values, "code.deps_recent", "repository", "web").missing == "not run — lookups off"
    )
    assert signals.words["code.deps_recent"] == "not run — lookups off"
