"""`ProcessAnalysisTools` over the real process runner and a stub tool (story 5.2, AC9)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from tests.unit.fakes.analysis_tools import FakeAnalysisTools

from orchestrator.domain.ports.analysis_tools import AnalysisTools
from orchestrator.infrastructure.analysis.tools import NOT_STARTED_EXIT, ProcessAnalysisTools
from orchestrator.infrastructure.process.runner import RealProcessRunner

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analysis"

STUB = """#!/bin/sh
echo "$0 $@" >> "{calls}"
if [ "$1" = "version" ]; then
  echo "gitleaks version 8.30.1"
  exit 0
fi
env
while [ $# -gt 0 ]; do
  if [ "$1" = "--report-path" ]; then
    cp "{sarif}" "$2"
  fi
  shift
done
exit 1
"""


def stub(tmp_path: Path, body: str | None = None) -> Path:
    script = tmp_path / "bin" / "gitleaks"
    script.parent.mkdir(exist_ok=True)
    text = body or STUB.replace("{sarif}", str(FIXTURES / "gitleaks.sarif")).replace(
        "{calls}", str(tmp_path / "calls")
    )
    script.write_text(text)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def tools(tmp_path: Path, script: Path) -> ProcessAnalysisTools:
    return ProcessAnalysisTools(
        RealProcessRunner(), tmp_path / "logs", binaries={"gitleaks": str(script)}
    )


def test_a_stub_gitleaks_reports_its_exit_its_version_and_gets_only_the_runners_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-not-for-tools")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-not-for-tools")
    report = tmp_path / "out.sarif"
    run = tools(tmp_path, stub(tmp_path)).run(
        "gitleaks", ["dir", str(tmp_path), "--report-path", str(report)], tmp_path, 1
    )
    assert run.exit == 1
    assert run.version == "8.30.1"
    assert run.timed_out is False
    assert report.read_text() == (FIXTURES / "gitleaks.sarif").read_text()
    assert "PATH=" in run.stdout
    assert "GITHUB_TOKEN" not in run.stdout
    assert "LITELLM" not in run.stdout
    assert list((tmp_path / "logs").iterdir()) == []


def test_the_version_is_read_once_per_tool(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    adapter = tools(tmp_path, stub(tmp_path))
    adapter.run("gitleaks", ["dir", "x"], tmp_path, 1)
    adapter.run("gitleaks", ["dir", "y"], tmp_path, 1)
    lines = calls.read_text().splitlines()
    assert sum(" version" in line for line in lines) == 1
    assert len(lines) == 3


def test_a_tool_that_prints_no_version_is_unknown(tmp_path: Path) -> None:
    script = stub(tmp_path, "#!/bin/sh\necho hello\n")
    assert tools(tmp_path, script).run("gitleaks", ["x"], tmp_path, 1).version == "unknown"


def test_an_unlisted_tool_runs_by_its_own_name_with_the_default_version_flag(
    tmp_path: Path,
) -> None:
    adapter = ProcessAnalysisTools(RealProcessRunner(), tmp_path / "logs")
    run = adapter.run("sh", ["-c", "echo done"], tmp_path, 1)
    assert run.exit == 0
    assert "done" in run.stdout


def test_a_timeout_has_no_exit_code(tmp_path: Path) -> None:
    script = stub(
        tmp_path, '#!/bin/sh\nif [ "$1" = "version" ]; then echo 8.1.0; exit 0; fi\nsleep 30\n'
    )
    run = tools(tmp_path, script).run("gitleaks", ["dir"], tmp_path, 0.001)
    assert run.exit is None
    assert run.timed_out is True
    assert run.version == "8.1.0"


def test_both_adapters_satisfy_the_port(tmp_path: Path) -> None:
    assert isinstance(ProcessAnalysisTools(RealProcessRunner(), tmp_path), AnalysisTools)
    assert isinstance(FakeAnalysisTools(), AnalysisTools)


def test_a_missing_tool_is_an_exit_not_an_exception_and_leaves_no_log(tmp_path: Path) -> None:
    """Review of story 5.2 (2026-11-13): an absent binary reads as the shell's 127."""
    adapter = tools(tmp_path, tmp_path / "bin" / "absent")
    run = adapter.run("gitleaks", ["dir", "x"], tmp_path, 1)
    assert run.exit == NOT_STARTED_EXIT == 127
    assert run.timed_out is False
    assert run.version == "unknown"
    assert str(tmp_path / "bin" / "absent") in run.stdout
    assert list((tmp_path / "logs").iterdir()) == []


def test_an_unread_version_is_probed_again(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    body = f'#!/bin/sh\necho "$1" >> "{calls}"\necho hello\n'
    adapter = tools(tmp_path, stub(tmp_path, body))
    adapter.run("gitleaks", ["dir"], tmp_path, 1)
    adapter.run("gitleaks", ["dir"], tmp_path, 1)
    assert calls.read_text().splitlines().count("version") == 2
