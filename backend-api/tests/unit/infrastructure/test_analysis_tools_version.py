"""`ProcessAnalysisTools.version`: a tool's installed version without running it on anything.

Epic 5 story 3, Operator ruling 2026-11-13: the toolset fingerprint holds every Tier 1 tool's
installed version, whether or not an analysis runs it.
"""

from __future__ import annotations

from pathlib import Path

from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.infrastructure.test_analysis_tools import stub, tools

from orchestrator.domain.ports.analysis_tools import ToolRun


def test_the_installed_version_is_probed_once_and_shared_with_the_runs(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    adapter = tools(tmp_path, stub(tmp_path))
    assert adapter.version("gitleaks") == "8.30.1"
    assert adapter.version("gitleaks") == "8.30.1"
    adapter.run("gitleaks", ["dir", "x"], tmp_path, 1)
    lines = calls.read_text().splitlines()
    assert sum(" version" in line for line in lines) == 1
    assert len(lines) == 2


def test_a_tool_that_is_not_installed_has_an_unknown_version(tmp_path: Path) -> None:
    adapter = tools(tmp_path, stub(tmp_path))
    assert adapter.version("no-such-analysis-tool") == "unknown"


def test_the_fake_answers_the_scripted_version_and_records_the_probe_apart() -> None:
    fake = FakeAnalysisTools({"lizard": ToolRun(0, "", "", "1.26.0")})
    assert fake.version("lizard") == "1.26.0"
    assert fake.version("jscpd") == "unknown"
    assert fake.version_calls == ["lizard", "jscpd"]
    assert fake.calls == []
