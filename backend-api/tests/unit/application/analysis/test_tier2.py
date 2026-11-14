"""Tier 2: the repository's own commands at base, head and fail-to-pass (epic 6 story 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.analysis.declaration import Declaration
from orchestrator.application.analysis.inputs import RepositoryInputs, slug
from orchestrator.application.analysis.tier2 import (
    NOT_DECLARED,
    TIER2_IDS,
    Tier2Ports,
    Tier2Result,
    collect_tier2,
    command_env,
)
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.process import Outcome
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace

COVERED = 30
TWO_SIDES = 2
THREE_CHECKOUTS = 3
FOUR_NEW = 4
ANALYSIS_ID = UUID(int=5)
SCRATCH = Path(f"/work/analysis/{ANALYSIS_ID}/root")
REL = f"{ANALYSIS_ID}/{slug('.')}"
NOW = datetime(2026, 11, 13, tzinfo=UTC)
TIMED_OUT = Outcome(exit_code=None, timed_out=True)
FAILED = Outcome(exit_code=1, timed_out=False)
COBERTURA = (
    '<coverage><class filename="src/app.py"><lines>'
    + "".join(f'<line number="{n}" hits="{1 if n <= COVERED else 0}"/>' for n in range(1, 41))
    + "</lines></class></coverage>"
)
BASE_JUNIT = (
    "<testsuite>"
    + "".join(
        f'<testcase classname="t" name="n{i}" file="tests/unit/test_x.py"/>' for i in range(10)
    )
    + "</testsuite>"
)
HEAD_JUNIT = (
    "<testsuite>"
    + "".join(
        f'<testcase classname="t" name="n{i}" file="tests/unit/test_x.py"/>' for i in range(1, 10)
    )
    + "".join(
        f'<testcase classname="t" name="new{i}" file="tests/unit/test_x.py"/>' for i in range(4)
    )
    + "</testsuite>"
)
ADDED_40 = "+++ b/src/app.py\n@@ -0,0 +1,40 @@\n" + "+x\n" * 40


def ids(result: Tier2Result) -> dict[str, dict[str | None, int]]:
    out: dict[str, dict[str | None, int]] = {}
    for c in result.counts:
        out.setdefault(c.metric_id, {})[c.source] = c.value
    return out


class Harness:
    def __init__(  # noqa: PLR0913 — one keyword per scripted part of the world
        self,
        commands: dict[str, str],
        *,
        files: dict[str, str] | None = None,
        outcomes: dict[str, Outcome] | None = None,
        name_status: tuple[NameStatus, ...] = (),
        diff: str = "",
        tier2: bool = True,
        git: FakeGit | None = None,
        worktree_add: list[object] | None = None,
    ) -> None:
        analysis = Analysis(
            id=ANALYSIS_ID,
            run_id=UUID(int=1),
            repository_path=".",
            base="b1",
            head="h1",
            status="ok",
            created_at=NOW,
        )
        declaration = Declaration(tier2=tier2, commands=commands)
        self.prepared = RepositoryInputs(analysis, SCRATCH, declaration, (), False)
        self.git = git or FakeGit(
            analysis=AnalysisScript(
                name_status={("b1", "h1"): name_status}, diff_text={("b1", "h1"): diff}
            ),
            worktree_add=worktree_add,
        )
        self.workspace = FakeWorkspace("/work/analysis", dict(files or {}))
        self.runner = FakeProcessRunner(outcomes=outcomes)
        self.env = {"NODE_ENV": "test"}

    def run(self, *, ports: bool = True) -> Tier2Result:
        numbers = count(1)
        return collect_tier2(
            self.prepared,
            git=self.git,
            scratch_root=self.workspace,
            ports=Tier2Ports(self.runner, 7, self.env) if ports else None,
            new_id=lambda: UUID(int=next(numbers) + 100),
        )

    def starts(self, command: str) -> list[dict[str, object]]:
        return [c for c in self.runner.called("start") if c["cmd"] == command]


def log(side: str, kind: str) -> str:
    return f"{REL}.tier2-logs/{side}-{kind}.log"


def report(side: str, path: str) -> str:
    return f"{REL}.tier2-{side}/{path}"


def test_without_a_declaration_every_signal_is_not_declared_and_nothing_starts() -> None:
    harness = Harness({"lint": "L"}, tier2=False)
    result = harness.run()
    assert result.words == dict.fromkeys(TIER2_IDS, NOT_DECLARED)
    assert harness.runner.calls == []
    assert NOT_DECLARED == "n/a — tier 2 not declared"


def test_without_a_runner_every_signal_is_not_run() -> None:
    result = Harness({"lint": "L"}).run(ports=False)
    assert set(result.words) == set(TIER2_IDS)
    assert result.words["code.fail_to_pass"] == "not run — no command runner"


def test_new_linter_warnings_and_type_errors_match_on_path_after_renames_and_message() -> None:
    base = "src/a.py:3:1: E1 unused\nsrc/b.py:9:4: W2 long line\n"
    head = "src/c.py:40:1: E1 unused\nsrc/b.py:12:4: W2 long line\nsrc/b.py:20:1: W3 new\n"
    ts_base = ""
    ts_head = "src/x.ts(3,5): error TS2322: nope\n"
    harness = Harness(
        {"lint": "L", "typecheck": "T"},
        files={
            log("base", "lint"): base,
            log("head", "lint"): head,
            log("base", "typecheck"): ts_base,
            log("head", "typecheck"): ts_head,
        },
        name_status=(NameStatus("R", "src/c.py", "src/a.py"),),
    )
    result = harness.run()
    figures = ids(result)
    assert figures["code.linter_warnings_new"] == {None: 1}
    assert figures["code.typecheck_errors_new"] == {None: 1}
    assert result.words == {
        "code.coverage_changed_lines": "n/a — no coverage command declared",
        "code.tests_executed": "n/a — no test_report command declared",
        "code.fail_to_pass": "n/a — no test_report command declared",
    }
    assert {c["cwd"] for c in harness.runner.called("start")} == {
        Path(f"{SCRATCH}.tier2-base"),
        Path(f"{SCRATCH}.tier2-head"),
    }
    assert {t.tool for t in result.artifacts} >= {"tier2:head:lint", "tier2:base:typecheck"}


def test_a_timed_out_command_is_started_once_per_side_and_its_output_stored() -> None:
    harness = Harness(
        {"lint": "L"}, files={log("head", "lint"): "partial output"}, outcomes={"L": TIMED_OUT}
    )
    result = harness.run()
    assert result.words["code.linter_warnings_new"] == "not run — timeout"
    assert len(harness.starts("L")) == TWO_SIDES
    assert {c["timeout_min"] for c in harness.runner.called("start")} == {7}
    stored = {a.tool: a.body for a in result.artifacts}
    assert stored["tier2:head:lint"] == b"partial output"


def test_every_command_gets_the_project_env_without_any_credential() -> None:
    harness = Harness({"lint": "L"})
    harness.env = {
        "GITHUB_TOKEN": "x",
        "LITELLM_API_KEY": "x",
        "LITELLM_SPEND_KEY": "x",
        "LANGFUSE_SECRET_KEY": "x",
        "ORCHESTRATOR_TOKEN": "x",
        "DATABASE_URL": "x",
        "NODE_ENV": "production",
    }
    harness.run()
    assert {tuple(c["env"]) for c in harness.runner.called("start")} == {("NODE_ENV",)}
    assert command_env({"OTEL_LOG_X": "1", "A": "2"}) == {"A": "2"}


def test_the_project_env_is_not_in_the_ports_repr() -> None:
    assert "secret" not in repr(Tier2Ports(FakeProcessRunner(), 1, {"K": "secret"}))


def test_coverage_of_the_added_production_lines_from_the_head_report() -> None:
    harness = Harness(
        {"coverage": "C", "coverage_report": "cov.xml"},
        files={report("head", "cov.xml"): COBERTURA},
        name_status=(NameStatus("A", "src/app.py", None),),
        diff=ADDED_40 + "+++ b/docs/readme.md\n@@ -0,0 +1 @@\n+hi\n",
    )
    result = harness.run()
    assert ids(result)["code.coverage_changed_lines"] == {
        "covered": 30,
        "instrumented": 40,
        "not_in_report": 0,
    }
    assert len(harness.git.called("worktree_add")) == 1


@pytest.mark.parametrize(
    ("files", "word"),
    [
        ({}, "not run — no report at cov.xml"),
        ({report("head", "cov.xml"): "<nope"}, "not run — report unreadable: cov.xml"),
    ],
)
def test_a_missing_or_unreadable_coverage_report_is_not_run(
    files: dict[str, str], word: str
) -> None:
    result = Harness({"coverage": "C", "coverage_report": "cov.xml"}, files=files).run()
    assert result.words["code.coverage_changed_lines"] == word


def test_a_timed_out_coverage_command_is_not_run() -> None:
    result = Harness(
        {"coverage": "C", "coverage_report": "cov.xml"}, outcomes={"C": TIMED_OUT}
    ).run()
    assert result.words["code.coverage_changed_lines"] == "not run — timeout"


def test_a_declared_command_without_its_report_path_reads_na() -> None:
    result = Harness({"coverage": "C", "test_report": "R"}).run()
    assert result.words["code.coverage_changed_lines"] == "n/a — no coverage report path declared"
    assert result.words["code.tests_executed"] == "n/a — no test report path declared"
    assert result.words["code.fail_to_pass"] == "n/a — no test report path declared"


def f2p_harness(f2p_report: str | None, **extra: object) -> Harness:
    files = {
        report("base", "junit.xml"): BASE_JUNIT,
        report("head", "junit.xml"): HEAD_JUNIT,
    }
    if f2p_report is not None:
        files[report("f2p", "junit.xml")] = f2p_report
    git = FakeGit(
        analysis=AnalysisScript(
            name_status={
                ("b1", "h1"): (
                    NameStatus("A", "tests/unit/test_x.py", None),
                    NameStatus("M", "tests/unit/test_old.py", None),
                    NameStatus("A", "src/app.py", None),
                    NameStatus("R", "tests/unit/test_r.py", "tests/unit/test_q.py"),
                )
            }
        ),
        files={("h1", "tests/unit/test_x.py"): "x", ("h1", "tests/unit/test_r.py"): "r"},
    )
    return Harness(
        {"test_report": "R", "test_report_path": "junit.xml", "install": "I"},
        files=files,
        git=git,
        **extra,  # type: ignore[arg-type]
    )


def _case(name: str, child: str) -> str:
    return f'<testcase classname="t" name="{name}" file="tests/unit/test_x.py">{child}</testcase>'


F2P_REPORT = (
    "<testsuite>"
    + _case("new0", '<failure message="AssertionError: a"/>')
    + _case("new1", '<error message="AssertionError: b"/>')
    + _case("new2", '<error message="ModuleNotFoundError: no m"/>')
    + _case("new3", "<skipped/>")
    + "</testsuite>"
)


def test_test_cases_executed_per_class_and_the_new_cases_that_fail_at_base() -> None:
    harness = f2p_harness(F2P_REPORT)
    result = harness.run()
    figures = ids(result)
    assert figures["code.tests_executed"] == {
        "test_unit:added": 4,
        "test_unit:removed": 1,
        "test_unit:total": 13,
    }
    assert figures["code.fail_to_pass"] == {
        "fail": 2,
        "pass": 0,
        "import_error": 1,
        "skipped": 1,
        "not_run": 0,
    }
    listed = next(a for a in result.artifacts if a.tool == "fail_to_pass")
    assert listed.media_type == "application/json"
    assert b'"reason": "AssertionError: a"' in listed.body
    assert b'"reason": "import error"' in listed.body
    assert [c["cwd"] for c in harness.runner.called("start") if c["cmd"] == "R"][-1] == Path(
        f"{SCRATCH}.tier2-f2p"
    )
    assert harness.workspace.read(report("f2p", "tests/unit/test_x.py")) == "x"
    assert harness.workspace.read(report("f2p", "tests/unit/test_r.py")) == "r"
    assert harness.workspace.read(report("f2p", "src/app.py")) is None
    assert len(harness.git.called("worktree_add")) == THREE_CHECKOUTS


def test_passed_absent_and_import_error_by_stem_are_told_apart() -> None:
    produced = """<testsuite>
<testcase classname="t" name="new0" file="tests/unit/test_x.py"/>
<testcase classname="tests.unit.test_x" name="collect"><error message="ImportError: z"/></testcase>
</testsuite>"""
    result = f2p_harness(produced).run()
    assert ids(result)["code.fail_to_pass"] == {
        "fail": 0,
        "pass": 1,
        "import_error": 3,
        "skipped": 0,
        "not_run": 0,
    }


def test_a_new_case_missing_from_the_report_is_not_run_when_nothing_explains_it() -> None:
    result = f2p_harness("<testsuite/>").run()
    assert ids(result)["code.fail_to_pass"]["not_run"] == FOUR_NEW


F2P_IMPORT = '<testsuite><testcase name="e"><error message="ImportError"/></testcase></testsuite>'


def test_cases_without_a_file_are_unclassified_and_cannot_be_explained_by_a_stem() -> None:
    base = "<testsuite/>"
    head = '<testsuite><testcase classname="c" name="a"/></testsuite>'
    harness = Harness(
        {"test_report": "R", "test_report_path": "junit.xml"},
        files={
            report("base", "junit.xml"): base,
            report("head", "junit.xml"): head,
            report("f2p", "junit.xml"): F2P_IMPORT,
        },
    )
    figures = ids(harness.run())
    assert figures["code.tests_executed"] == {
        "unclassified:added": 1,
        "unclassified:removed": 0,
        "unclassified:total": 1,
    }
    assert figures["code.fail_to_pass"]["not_run"] == 1


def test_a_missing_or_unreadable_test_report_is_not_run() -> None:
    harness = f2p_harness(F2P_REPORT)
    harness.workspace.remove(report("head", "junit.xml"))
    assert harness.run().words["code.tests_executed"] == "not run — no report at junit.xml"
    harness = f2p_harness(F2P_REPORT)
    harness.workspace.write(report("base", "junit.xml"), "<x")
    assert harness.run().words["code.fail_to_pass"] == "not run — report unreadable: junit.xml"


class _F2pTimeout(FakeProcessRunner):
    """Times out only the commands run in the fail-to-pass checkout."""

    def start(self, cmd, **kwargs):  # type: ignore[no-untyped-def]
        handle = super().start(cmd, **kwargs)
        if str(kwargs["cwd"]).endswith("f2p") and cmd == "R":
            self._pending[handle.pgid] = TIMED_OUT
        return handle


def test_the_f2p_report_missing_or_its_run_timed_out_only_affects_fail_to_pass() -> None:
    result = f2p_harness(None).run()
    assert result.words["code.fail_to_pass"] == "not run — no report at junit.xml"
    assert "code.tests_executed" in ids(result)
    harness = f2p_harness(F2P_REPORT)
    harness.runner = _F2pTimeout()
    result = harness.run()
    assert result.words["code.fail_to_pass"] == "not run — timeout"
    assert "code.tests_executed" in ids(result)
    harness = f2p_harness("<nope")
    assert harness.run().words["code.fail_to_pass"] == "not run — report unreadable: junit.xml"


def test_a_failed_install_is_not_run_for_every_signal_of_that_side() -> None:
    harness = f2p_harness(F2P_REPORT)
    harness.runner = FakeProcessRunner(outcomes={"I": FAILED})
    result = harness.run()
    assert result.words["code.tests_executed"] == "not run — install exit 1"
    assert len(harness.starts("R")) == 0


def test_a_timed_out_install_is_a_timeout() -> None:
    harness = f2p_harness(F2P_REPORT)
    harness.runner = FakeProcessRunner(outcomes={"I": TIMED_OUT})
    assert harness.run().words["code.fail_to_pass"] == "not run — install timeout"


def test_a_failed_checkout_is_not_run_for_every_declared_signal() -> None:
    harness = Harness(
        {"lint": "L", "test_report": "R", "test_report_path": "j.xml"},
        worktree_add=[GitError(command="git worktree add", exit_code=128, output="boom")],
    )
    result = harness.run()
    assert result.words == {
        "code.linter_warnings_new": "not run — checkout failed",
        "code.tests_executed": "not run — checkout failed",
        "code.fail_to_pass": "not run — checkout failed",
        "code.typecheck_errors_new": "n/a — no typecheck command declared",
        "code.coverage_changed_lines": "n/a — no coverage command declared",
    }
    assert harness.runner.calls == []


def test_a_checkout_failure_without_a_test_report_leaves_that_signal_alone() -> None:
    harness = Harness(
        {"lint": "L"},
        worktree_add=[GitError(command="git worktree add", exit_code=128, output="boom")],
    )
    assert harness.run().words["code.linter_warnings_new"] == "not run — checkout failed"


class _BinaryGit(FakeGit):
    def read_file(self, dest: Path, ref: str, path: str) -> str | None:
        if path.endswith("bin.py"):
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        return None if path.endswith("none.py") else "text"


def test_a_test_file_that_is_not_text_or_unreadable_is_not_copied() -> None:
    git = _BinaryGit(
        analysis=AnalysisScript(
            name_status={
                ("b1", "h1"): (
                    NameStatus("A", "tests/unit/test_bin.py", None),
                    NameStatus("A", "tests/unit/test_none.py", None),
                    NameStatus("A", "tests/unit/test_ok.py", None),
                )
            }
        )
    )
    harness = Harness(
        {"test_report": "R", "test_report_path": "j.xml"},
        files={report(s, "j.xml"): "<testsuite/>" for s in ("base", "head", "f2p")},
        git=git,
    )
    harness.run()
    assert harness.workspace.read(report("f2p", "tests/unit/test_ok.py")) == "text"
    assert harness.workspace.read(report("f2p", "tests/unit/test_none.py")) is None


class _StrictWorkspace(FakeWorkspace):
    """`read` decodes strictly, as the filesystem adapter does on undecodable bytes."""

    def read(self, path: str) -> str | None:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    def read_lenient(self, path: str) -> str | None:
        return super().read(path)


def test_command_output_and_reports_are_read_leniently_so_bad_bytes_never_fail_the_analysis() -> (
    None
):
    files = {log("head", "lint"): "src/b.py:1:1: W3 new\n", report("head", "cov.xml"): COBERTURA}
    harness = Harness({"lint": "L", "coverage": "C", "coverage_report": "cov.xml"}, diff=ADDED_40)
    harness.workspace = _StrictWorkspace("/work/analysis", files)
    result = harness.run()
    figures = ids(result)
    assert figures["code.linter_warnings_new"] == {None: 1}
    assert figures["code.coverage_changed_lines"]["covered"] == COVERED


def test_an_added_test_file_that_cannot_be_written_at_base_is_skipped_not_fatal() -> None:
    git = _BinaryGit(
        analysis=AnalysisScript(
            name_status={
                ("b1", "h1"): (
                    NameStatus("A", "tests/unit/test_ok.py", None),
                    NameStatus("A", "tests/unit/test_dir.py", None),
                )
            }
        )
    )
    files = {report(s, "j.xml"): "<testsuite/>" for s in ("base", "head", "f2p")}
    files[report("f2p", "tests/unit/test_dir.py/inner")] = "a folder at base"
    harness = Harness({"test_report": "R", "test_report_path": "j.xml"}, files=files, git=git)
    result = harness.run()
    assert harness.workspace.read(report("f2p", "tests/unit/test_ok.py")) == "text"
    assert "code.fail_to_pass" in ids(result)


def test_no_fail_to_pass_checkout_when_the_base_or_head_test_report_already_failed() -> None:
    harness = Harness(
        {"test_report": "R", "test_report_path": "j.xml"},
        outcomes={"R": TIMED_OUT},
        name_status=(NameStatus("A", "tests/unit/test_new.py", None),),
    )
    result = harness.run()
    assert result.words["code.fail_to_pass"] == "not run — timeout"
    assert {c["cwd"] for c in harness.runner.called("start")} == {
        Path(f"{SCRATCH}.tier2-base"),
        Path(f"{SCRATCH}.tier2-head"),
    }
