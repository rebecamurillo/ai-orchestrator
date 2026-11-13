"""The gitleaks scan over added lines (story 5.2, AC4)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.analysis.secrets import (
    ADDED_FILES,
    GITLEAKS,
    GITLEAKS_COMMAND,
    GITLEAKS_TIMEOUT_MIN,
    SARIF_MEDIA_TYPE,
    scan_secrets,
)
from orchestrator.domain.ports.analysis_tools import ToolRun
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.workspace import FakeWorkspace

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis"
SARIF = (FIXTURES / "gitleaks.sarif").read_text()
ANALYSIS = UUID(int=7)
ROOT = Path("/work/analysis")
RELATIVE = f"{ANALYSIS}/root"
CLONE = ROOT / RELATIVE
ADDED = {"src/a.ts": ("one", "two"), "docs/b.md": ("three",)}


def scan(
    tools: FakeAnalysisTools,
    workspace: FakeWorkspace,
    added: dict[str, tuple[str, ...]] | None = None,
) -> object:
    return scan_secrets(
        ADDED if added is None else added,
        scratch_root=workspace,
        scratch_path=CLONE,
        relative=RELATIVE,
        tools=tools,
        analysis_id=ANALYSIS,
        new_id=lambda: UUID(int=99),
    )


def test_the_recorded_report_counts_one_result_and_is_kept_as_the_artefact() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(1, "", "", "8.30.1")}, {GITLEAKS: SARIF}, workspace, ROOT
    )
    result = scan(tools, workspace)
    assert result.count == 1  # type: ignore[attr-defined]
    assert result.missing is None  # type: ignore[attr-defined]
    assert result.version == "8.30.1"  # type: ignore[attr-defined]
    artifact = result.artifact  # type: ignore[attr-defined]
    assert artifact.tool == "gitleaks"
    assert artifact.media_type == SARIF_MEDIA_TYPE == "application/sarif+json"
    assert artifact.body == SARIF.encode()
    assert artifact.analysis_id == ANALYSIS
    assert artifact.id == UUID(int=99)


def test_only_the_added_lines_are_written_inside_the_analysis_folder_and_the_command_is_exact() -> (
    None
):
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(0, "", "", "8.30.1")}, {GITLEAKS: SARIF}, workspace, ROOT
    )
    scan(tools, workspace)
    assert workspace.read(f"{RELATIVE}.added/{ADDED_FILES}/src/a.ts") == "one\ntwo"
    assert workspace.read(f"{RELATIVE}.added/{ADDED_FILES}/docs/b.md") == "three"
    (call,) = tools.calls
    assert call["tool"] == GITLEAKS
    assert call["args"] == (
        "dir",
        f"{CLONE}.added",
        "--report-format",
        "sarif",
        "--report-path",
        f"{CLONE}.gitleaks.sarif",
        "--redact",
        "--no-banner",
        "--ignore-gitleaks-allow",
    )
    assert call["cwd"] == CLONE.parent
    assert call["timeout"] == GITLEAKS_TIMEOUT_MIN == 10
    assert GITLEAKS_COMMAND[0] == GITLEAKS


def test_no_added_lines_is_zero_without_a_run() -> None:
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools()
    for added in ({}, {"a.ts": ()}):
        result = scan(tools, workspace, added)
        assert result.count == 0  # type: ignore[attr-defined]
        assert result.artifact is None  # type: ignore[attr-defined]
        assert result.missing is None  # type: ignore[attr-defined]
        assert result.version == ""  # type: ignore[attr-defined]
    assert tools.calls == []


def test_a_clean_run_with_an_empty_report_is_zero() -> None:
    workspace = FakeWorkspace()
    empty = '{"runs": [{"results": []}]}'
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(0, "", "", "8.30.1")}, {GITLEAKS: empty}, workspace, ROOT
    )
    result = scan(tools, workspace)
    assert result.count == 0  # type: ignore[attr-defined]
    assert result.artifact.body == empty.encode()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("run", "report", "reason"),
    [
        (ToolRun(2, "boom\nmore", "", "8.30.1"), SARIF, "gitleaks: exit 2: boom"),
        (ToolRun(None, "", "", "8.30.1", timed_out=True), SARIF, "gitleaks: timed out"),
        (ToolRun(1, "", "", "8.30.1"), None, "gitleaks: no report"),
        (ToolRun(1, "", "", "8.30.1"), "{not json", "gitleaks: report unreadable"),
        (ToolRun(1, "", "", "8.30.1"), '{"version": "2.1.0"}', "gitleaks: report unreadable"),
        (ToolRun(2, "", "", "8.30.1"), SARIF, "gitleaks: exit 2"),
    ],
)
def test_a_scan_that_did_not_finish_is_a_word_with_no_artefact(
    run: ToolRun, report: str | None, reason: str
) -> None:
    workspace = FakeWorkspace()
    writes = {} if report is None else {GITLEAKS: report}
    result = scan(FakeAnalysisTools({GITLEAKS: run}, writes, workspace, ROOT), workspace)
    assert result.count is None  # type: ignore[attr-defined]
    assert result.artifact is None  # type: ignore[attr-defined]
    assert result.missing == f"not run — {reason}"  # type: ignore[attr-defined]


def test_files_the_change_adds_cannot_configure_the_scan() -> None:
    """Review of story 5.2 (2026-11-13): gitleaks reads `.gitleaks.toml` and `.gitleaksignore`
    from the root it scans and honours inline `gitleaks:allow`; the change under measure must
    reach none of them."""
    workspace = FakeWorkspace()
    tools = FakeAnalysisTools(
        {GITLEAKS: ToolRun(1, "", "", "8.30.1")}, {GITLEAKS: SARIF}, workspace, ROOT
    )
    added = {".gitleaks.toml": ("[allowlist]",), ".gitleaksignore": ("x",), "a.ts": ("k",)}
    scan(tools, workspace, added)
    (call,) = tools.calls
    scanned = call["args"][1]
    assert scanned == f"{CLONE}.added"
    assert workspace.read(f"{RELATIVE}.added/.gitleaks.toml") is None
    assert workspace.read(f"{RELATIVE}.added/.gitleaksignore") is None
    assert workspace.read(f"{RELATIVE}.added/{ADDED_FILES}/.gitleaks.toml") == "[allowlist]"
    assert "--ignore-gitleaks-allow" in call["args"]
