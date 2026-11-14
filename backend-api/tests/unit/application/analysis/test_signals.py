"""Per-repository signals: collect, store, and the JSON the pending summary is kept as
(story 5.2, AC4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.secrets import GITLEAKS
from orchestrator.application.analysis.signals import (
    RepositorySignals,
    collect_tier1a,
    signals_from_json,
    signals_to_json,
    store_signals,
)
from orchestrator.application.analysis.tier1a import Count
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.workspace import FakeWorkspace

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis"
SARIF = (FIXTURES / "gitleaks.sarif").read_text()
ROOT = Path("/work/analysis")
ANALYSIS_ID = UUID(int=5)
NOW = datetime(2026, 11, 13, tzinfo=UTC)
DIFF = (
    "diff --git a/src/a.ts b/src/a.ts\n--- a/src/a.ts\n+++ b/src/a.ts\n@@ -1 +1,2 @@\n-x\n"
    "+const a = v as any;\n+const b = 1;\n"
)


def analysis(status: str = "ok", output: str = "") -> Analysis:
    return Analysis(
        id=ANALYSIS_ID,
        run_id=UUID(int=1),
        calculation_id=UUID(int=2),
        repository_path=".",
        base="b1",
        head="h1",
        status=status,  # type: ignore[arg-type]
        output=output,
        created_at=NOW,
    )


def prepared(status: str = "ok", output: str = "") -> RepositoryInputs:
    return RepositoryInputs(
        analysis(status, output), ROOT / f"{ANALYSIS_ID}/root", DEFAULT_DECLARATION, (), False
    )


def git() -> FakeGit:
    script = AnalysisScript(
        numstat={("b1", "h1"): (NumstatEntry("src/a.ts", 2, 1, False),)},
        name_status={("b1", "h1"): (NameStatus("M", "src/a.ts", None),)},
        diff_text={("b1", "h1"): DIFF},
    )
    return FakeGit(analysis=script)


def collect(tools: FakeAnalysisTools, workspace: FakeWorkspace, fake: FakeGit) -> RepositorySignals:
    return collect_tier1a(
        prepared(), git=fake, scratch_root=workspace, tools=tools, new_id=lambda: UUID(int=77)
    )


def test_collect_counts_the_diff_and_scans_the_added_lines() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(1, "", "", "8.30.1")}, {GITLEAKS: SARIF}, workspace, ROOT
    )
    signals = collect(tools, workspace, git())
    assert signals.path == "."
    assert signals.status == "ok"
    table = {(c.metric_id, c.source): c.value for c in signals.counts}
    assert table[("code.lines_added", "production")] == 2
    assert table[("code.type_escapes_added", "production")] == 1
    assert table[("code.possible_secrets", None)] == 1
    assert signals.words == {}
    assert signals.tool_versions == {"gitleaks": "8.30.1"}
    (artifact,) = signals.artifacts
    assert (artifact.tool, artifact.media_type) == ("gitleaks", "application/sarif+json")
    assert artifact.body == SARIF.encode()
    assert (
        workspace.read(f"{ANALYSIS_ID}/root.added/files/src/a.ts")
        == "const a = v as any;\nconst b = 1;"
    )


def test_a_secrets_scan_that_failed_is_a_word_and_no_count() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools({GITLEAKS: ToolRun(2, "boom", "", "8.30.1")}, {}, workspace, ROOT)
    signals = collect(tools, workspace, git())
    assert ("code.possible_secrets", None) not in {(c.metric_id, c.source) for c in signals.counts}
    assert signals.words == {"code.possible_secrets": "not run — gitleaks: exit 2: boom"}
    assert signals.artifacts == ()


def test_a_diff_that_adds_no_lines_scans_nothing_and_counts_no_secrets() -> None:
    fake = FakeGit(
        analysis=AnalysisScript(
            numstat={("b1", "h1"): (NumstatEntry("src/a.ts", 0, 3, False),)},
            name_status={("b1", "h1"): (NameStatus("M", "src/a.ts", None),)},
        )
    )
    tools = FakeAnalysisTools()
    signals = collect(tools, FakeWorkspace(), fake)
    table = {(c.metric_id, c.source): c.value for c in signals.counts}
    assert table[("code.possible_secrets", None)] == 0
    assert table[("code.lines_removed", "production")] == 3
    assert signals.tool_versions == {}
    assert tools.calls == []


def test_a_failed_input_reads_nothing() -> None:
    fake = git()
    tools = FakeAnalysisTools()
    signals = collect_tier1a(
        prepared("failed", "no merge base: h1 and origin/main"),
        git=fake,
        scratch_root=FakeWorkspace(),
        tools=tools,
        new_id=lambda: UUID(int=77),
    )
    assert signals.status == "failed"
    assert signals.output == "no merge base: h1 and origin/main"
    assert signals.counts == ()
    assert signals.words == {}
    assert signals.artifacts == ()
    assert fake.calls == []
    assert tools.calls == []


def test_a_partial_input_is_still_read() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(0, "", "", "8.30.1")}, {GITLEAKS: SARIF}, workspace, ROOT
    )
    signals = collect_tier1a(
        prepared("partial", "unknown key: x"),
        git=git(),
        scratch_root=workspace,
        tools=tools,
        new_id=lambda: UUID(int=77),
    )
    assert signals.status == "partial"
    assert signals.output == "unknown key: x"
    assert signals.counts


def test_store_adds_the_analysis_then_each_artefact() -> None:
    repo = FakeAnalysisRepository()
    order: list[str] = []
    original_add, original_artifact = repo.add, repo.add_artifact
    repo.add = lambda a: (order.append("analysis"), original_add(a))[1]  # type: ignore[method-assign]
    repo.add_artifact = lambda a: (order.append(a.tool), original_artifact(a))[1]  # type: ignore[method-assign]
    artifacts = tuple(
        AnalysisArtifact(
            id=UUID(int=n), analysis_id=ANALYSIS_ID, tool=tool, media_type="x", body=b"y"
        )
        for n, tool in ((1, "gitleaks"), (2, "summary"))
    )
    signals = RepositorySignals(".", "ok", "", (), {}, artifacts, {})
    store_signals(repo, analysis(), signals)
    assert order == ["analysis", "gitleaks", "summary"]
    assert repo.rows == [analysis()]
    assert [a.tool for a in repo.artifacts] == ["gitleaks", "summary"]


def test_json_round_trip_leaves_the_artefacts_out() -> None:
    artifact = AnalysisArtifact(
        id=UUID(int=1), analysis_id=ANALYSIS_ID, tool="gitleaks", media_type="x", body=b"y"
    )
    signals = RepositorySignals(
        "web",
        "partial",
        "unknown key: x",
        (
            Count("code.suppressions_added", None, 2, "production"),
            Count("code.lines_added", "production", 30, None),
            Count("code.functions_over_cyclomatic", None, 4, None, "max"),
        ),
        {"code.possible_secrets": "not run — gitleaks: timed out"},
        (artifact,),
        {"gitleaks": "8.30.1"},
    )
    again = signals_from_json(signals_to_json(signals))
    assert again == RepositorySignals(
        signals.path,
        signals.status,
        signals.output,
        signals.counts,
        signals.words,
        (),
        signals.tool_versions,
    )
    assert isinstance(signals_to_json(signals), bytes)
