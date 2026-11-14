"""Opengrep over the changed files at base and head, matched new versus fixed (epic 6 story 2)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.findings import (
    BUG,
    FINDINGS_TOOL,
    OPENGREP,
    SECURITY,
    collect_findings,
)
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.git_analysis import NameStatus
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.workspace import FakeWorkspace

ROOT = Path("/work/analysis")
ANALYSIS_ID = UUID(int=5)
RELATIVE = f"{ANALYSIS_ID}/root"
SCRATCH = ROOT / RELATIVE
NOW = datetime(2026, 11, 13, tzinfo=UTC)
RULES = {"rules/a.yaml": "rule a", "rules/b.yaml": "rule b"}
OK = ToolRun(exit=0, stdout="", stderr="", version="2.0.0")
MOVED_LINE = 23
TIMEOUT_MIN = 10
BOTH_SIDES = 2
SECURITY_TAGS = ["security", "CWE-79: Improper Neutralization"]


def one_id(_: int = 0) -> UUID:
    return UUID(int=9)


def rule(rule_id: str, tags: list[str] | None = None, **props: Any) -> dict[str, Any]:
    return {"id": rule_id, "properties": {"tags": tags or [], **props}}


def hit(rule_id: str, path: str, line: int = 1, level: str = "warning") -> dict[str, Any]:
    location = {
        "physicalLocation": {
            "artifactLocation": {"uri": f"files/{path}", "uriBaseId": "%SRCROOT%"},
            "region": {"startLine": line},
        }
    }
    return {"ruleId": rule_id, "level": level, "locations": [location]}


def sarif(results: list[dict[str, Any]], rules: list[dict[str, Any]] | None = None) -> str:
    run = {"tool": {"driver": {"name": "Opengrep", "rules": rules or []}}, "results": results}
    return json.dumps({"version": "2.1.0", "runs": [run]})


R1 = rule("r1", SECURITY_TAGS)
R2 = rule("r2")
R3 = rule("r3", SECURITY_TAGS, **{"security-severity": "8.1"})
BASE_SARIF = sarif([hit("r1", "src/a.py", 3), hit("r2", "src/b.py")], [R1, R2])
HEAD_SARIF = sarif([hit("r1", "src/a.py", 23), hit("r3", "src/c.py")], [R1, R3])
SOURCES = {
    ("b1", "src/a.py"): "x\ny\nz",
    ("b1", "src/b.py"): "b",
    ("h1", "src/a.py"): "\n" * 22 + "   z",
    ("h1", "src/c.py"): "c",
    ("b1", "rules/a.yaml"): RULES["rules/a.yaml"],
    ("b1", "rules/b.yaml"): RULES["rules/b.yaml"],
}
CHANGES = (
    NameStatus("M", "src/a.py", None),
    NameStatus("D", "src/b.py", None),
    NameStatus("A", "src/c.py", None),
)


def inputs(rules: str | None = "rules/", scratch: Path | None = SCRATCH) -> RepositoryInputs:
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
    return RepositoryInputs(
        analysis, scratch, replace(DEFAULT_DECLARATION, sast_rules=rules), (), False
    )


def fake_git(
    changes: tuple[NameStatus, ...] = CHANGES,
    files: dict[tuple[str, str], str] | None = None,
    listing: tuple[str, ...] = tuple(RULES),
) -> FakeGit:
    return FakeGit(
        analysis=AnalysisScript(name_status={("b1", "h1"): changes}),
        files=SOURCES if files is None else files,
        listings={("b1", "rules/"): list(listing)},
    )


def collect(
    *,
    git: FakeGit | None = None,
    base: str | None = BASE_SARIF,
    head: str | None = HEAD_SARIF,
    run: ToolRun = OK,
    prepared: RepositoryInputs | None = None,
) -> tuple[Any, FakeAnalysisTools, FakeWorkspace]:
    workspace = FakeWorkspace(files={} if base is None else {f"{RELATIVE}.sast-base.sarif": base})
    if head is not None:
        workspace.write(f"{RELATIVE}.sast-head.sarif", head)
    tools = FakeAnalysisTools(runs={OPENGREP: run})
    result = collect_findings(
        prepared or inputs(),
        git=git or fake_git(),
        scratch_root=workspace,
        tools=tools,
        new_id=one_id,
    )
    return result, tools, workspace


def table(result: Any, metric: str) -> dict[str, int]:
    return {c.source: c.value for c in result.counts if c.metric_id == metric}


def listed(result: Any) -> dict[tuple[str, str], dict[str, Any]]:
    artifact = next(a for a in result.artifacts if a.tool == FINDINGS_TOOL)
    return {(f["rule"], f["state"]): f for f in json.loads(artifact.body)}


def test_new_fixed_and_unchanged_are_counted_by_kind_and_severity() -> None:
    result, _, _ = collect()
    assert table(result, SECURITY) == {"high": 1, "medium": 0, "low": 0, "fixed": 0, "unchanged": 1}
    assert table(result, BUG) == {"high": 0, "medium": 0, "low": 0, "fixed": 1, "unchanged": 0}
    assert all(c.rate is None for c in result.counts)
    assert result.words == {}


def test_the_security_severity_score_and_cwe_reach_the_findings_list() -> None:
    result, _, _ = collect()
    found = listed(result)
    assert found[("r3", "new")] == {
        "kind": "security",
        "rule": "r3",
        "path": "src/c.py",
        "line": 1,
        "severity": "high",
        "cwe": ["CWE-79"],
        "state": "new",
    }
    assert found[("r1", "unchanged")]["line"] == MOVED_LINE
    assert found[("r2", "absent")]["kind"] == "bug"
    assert result.artifacts[1].media_type == "application/json"


def test_each_result_of_the_stored_sarif_carries_its_baseline_state() -> None:
    result, _, _ = collect()
    artifact = next(a for a in result.artifacts if a.tool == OPENGREP)
    assert artifact.media_type == "application/sarif+json"
    assert artifact.analysis_id == ANALYSIS_ID
    stored = json.loads(artifact.body)
    results = stored["runs"][0]["results"]
    assert {r["ruleId"]: r["baselineState"] for r in results} == {
        "r1": "unchanged",
        "r3": "new",
        "r2": "absent",
    }
    assert stored["version"] == "2.1.0"
    assert str(ROOT) not in artifact.body.decode()
    assert "files/" not in artifact.body.decode()


def test_a_renamed_file_with_the_same_match_is_unchanged() -> None:
    changes = (NameStatus("R", "src/c.py", "src/b.py"),)
    git = fake_git(changes, {**SOURCES, ("h1", "src/c.py"): "b"})
    head = sarif([hit("r2", "src/c.py")], [R2])
    result, _, _ = collect(git=git, base=sarif([hit("r2", "src/b.py")], [R2]), head=head)
    assert table(result, BUG) == {"high": 0, "medium": 0, "low": 0, "fixed": 0, "unchanged": 1}


def test_two_head_matches_of_one_base_match_are_one_unchanged_and_one_new() -> None:
    base = sarif([hit("r2", "src/b.py")], [R2])
    head = sarif([hit("r2", "src/b.py", 1), hit("r2", "src/b.py", 1)], [R2])
    git = fake_git((NameStatus("M", "src/b.py", None),), {**SOURCES, ("h1", "src/b.py"): "b"})
    result, _, _ = collect(git=git, base=base, head=head)
    assert table(result, BUG) == {"high": 0, "medium": 1, "low": 0, "fixed": 0, "unchanged": 1}


def test_opengrep_runs_once_per_side_on_the_changed_files_in_the_scratch_folders() -> None:
    _, tools, workspace = collect()
    base, head = tools.calls
    assert base["tool"] == head["tool"] == OPENGREP
    assert base["cwd"] == Path(f"{SCRATCH}.sast-base")
    assert head["cwd"] == Path(f"{SCRATCH}.sast-head")
    assert base["timeout"] == TIMEOUT_MIN
    config = f"{SCRATCH}.sast-rules/rules"
    assert base["args"] == (
        *("scan", "--config", config),
        *("--sarif-output", f"{SCRATCH}.sast-base.sarif"),
        *("files/src/a.py", "files/src/b.py"),
    )
    assert head["args"][-2:] == ("files/src/a.py", "files/src/c.py")
    assert head["args"][4] == f"{SCRATCH}.sast-head.sarif"
    assert workspace.read(f"{RELATIVE}.sast-base/files/src/b.py") == "b"
    assert workspace.read(f"{RELATIVE}.sast-head/files/src/c.py") == "c"
    assert workspace.read(f"{RELATIVE}.sast-rules/rules/a.yaml") == "rule a"
    assert workspace.read(f"{RELATIVE}.sast-rules/rules/b.yaml") == "rule b"
    assert tools.version_calls == []


def test_a_renamed_file_is_scanned_at_base_under_its_old_path() -> None:
    changes = (NameStatus("R", "src/c.py", "src/b.py"), NameStatus("T", "src/a.py", None))
    git = fake_git(changes, {**SOURCES, ("h1", "src/c.py"): "b"})
    _, tools, _ = collect(git=git)
    assert tools.calls[0]["args"][-2:] == ("files/src/a.py", "files/src/b.py")
    assert tools.calls[1]["args"][-2:] == ("files/src/a.py", "files/src/c.py")


def test_the_toolset_record_carries_the_version_and_the_rule_pack_hash() -> None:
    result, _, _ = collect()
    pairs = sorted(
        [path, hashlib.sha256(text.encode()).hexdigest()] for path, text in RULES.items()
    )
    digest = hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()
    assert result.toolset == ({"tool": OPENGREP, "version": "2.0.0", "rule_pack_hash": digest},)
    assert result.tool_versions == {OPENGREP: "2.0.0"}


def test_another_rule_file_content_gives_another_rule_pack_hash() -> None:
    other = {**SOURCES, ("b1", "rules/b.yaml"): "changed"}
    one, _, _ = collect()
    two, _, _ = collect(git=fake_git(files=other))
    assert one.toolset[0]["rule_pack_hash"] != two.toolset[0]["rule_pack_hash"]


def test_a_single_rule_file_is_a_rule_pack_of_one() -> None:
    git = fake_git(files={**SOURCES, ("b1", "rules.yaml"): "r"})
    result, tools, workspace = collect(git=git, prepared=inputs("rules.yaml"))
    assert tools.calls[0]["args"][2] == f"{SCRATCH}.sast-rules/rules.yaml"
    assert workspace.read(f"{RELATIVE}.sast-rules/rules.yaml") == "r"
    assert result.words == {}


def test_a_rule_folder_git_also_shows_as_a_tree_listing_is_read_file_by_file() -> None:
    git = fake_git(files={**SOURCES, ("b1", "rules/"): "tree b1:rules/\n\na.yaml\nb.yaml\n"})
    result, _, workspace = collect(git=git)
    assert workspace.read(f"{RELATIVE}.sast-rules/rules/a.yaml") == "rule a"
    assert workspace.read(f"{RELATIVE}.sast-rules/rules/") is None
    assert result.words == {}


def test_a_declaration_without_rules_runs_and_probes_nothing() -> None:
    result, tools, workspace = collect(prepared=inputs(None))
    assert result.words == {
        SECURITY: "n/a — no rules declared",
        BUG: "n/a — no rules declared",
    }
    assert (result.counts, result.artifacts, result.toolset, result.tool_versions) == (
        (),
        (),
        (),
        {},
    )
    assert tools.calls == [] == tools.version_calls
    assert workspace.read(f"{RELATIVE}.sast-rules/rules/a.yaml") is None


@pytest.mark.parametrize("path", ["p/default", "/etc/rules", "../rules", "rules/../../x"])
def test_rules_that_name_nothing_at_base_run_nothing(path: str) -> None:
    result, tools, _ = collect(prepared=inputs(path))
    word = f"not run — opengrep: no rules at {path}"
    assert result.words == {SECURITY: word, BUG: word}
    assert tools.calls == []
    assert result.toolset[0]["rule_pack_hash"] is None
    assert result.toolset[0]["version"] == "2.0.0"
    assert tools.version_calls == [OPENGREP]
    assert result.counts == ()


def test_a_rule_file_that_cannot_be_read_is_left_out_of_the_pack() -> None:
    git = fake_git(files={k: v for k, v in SOURCES.items() if k != ("b1", "rules/b.yaml")})
    result, tools, _ = collect(git=git)
    pairs = [["rules/a.yaml", hashlib.sha256(b"rule a").hexdigest()]]
    digest = hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()
    assert result.toolset[0]["rule_pack_hash"] == digest
    assert len(tools.calls) == BOTH_SIDES


@pytest.mark.parametrize(
    ("run", "word"),
    [
        (ToolRun(None, "", "", "2.0.0", timed_out=True), "timed out"),
        (ToolRun(2, "boom\nmore", "", "2.0.0"), "exit 2: boom"),
        (ToolRun(3, "", "", "2.0.0"), "exit 3"),
    ],
)
def test_a_run_that_did_not_finish_stops_the_findings(run: ToolRun, word: str) -> None:
    result, tools, _ = collect(run=run)
    assert result.words == {
        SECURITY: f"not run — opengrep: {word}",
        BUG: f"not run — opengrep: {word}",
    }
    assert len(tools.calls) == 1
    assert (result.counts, result.artifacts) == ((), ())
    assert result.toolset[0]["version"] == "2.0.0"


def test_a_missing_report_is_no_report() -> None:
    result, tools, _ = collect(base=None)
    assert result.words[SECURITY] == "not run — opengrep: no report"
    assert len(tools.calls) == 1


def test_an_unparsable_report_is_report_unreadable_at_either_side() -> None:
    one, tools, _ = collect(base="nope")
    assert one.words[BUG] == "not run — opengrep: report unreadable"
    assert len(tools.calls) == 1
    two, tools, _ = collect(head="{}")
    assert two.words[BUG] == "not run — opengrep: report unreadable"
    assert len(tools.calls) == BOTH_SIDES


def test_a_side_without_changed_files_runs_nothing_and_adds_no_finding() -> None:
    added = (NameStatus("A", "src/c.py", None),)
    result, tools, _ = collect(git=fake_git(added), base=None)
    assert [c["cwd"] for c in tools.calls] == [Path(f"{SCRATCH}.sast-head")]
    assert table(result, SECURITY)["high"] == 1
    stored = json.loads(next(a for a in result.artifacts if a.tool == OPENGREP).body)
    assert {r["baselineState"] for r in stored["runs"][0]["results"]} == {"new"}

    removed = (NameStatus("D", "src/b.py", None),)
    result, tools, _ = collect(git=fake_git(removed), head=None)
    assert [c["cwd"] for c in tools.calls] == [Path(f"{SCRATCH}.sast-base")]
    assert table(result, BUG)["fixed"] == 1
    stored = json.loads(next(a for a in result.artifacts if a.tool == OPENGREP).body)
    assert {r["baselineState"] for r in stored["runs"][0]["results"]} == {"absent"}


def test_no_changed_file_to_scan_is_zero_findings_without_a_run() -> None:
    result, tools, _ = collect(git=fake_git(()))
    assert tools.calls == []
    assert table(result, SECURITY) == {"high": 0, "medium": 0, "low": 0, "fixed": 0, "unchanged": 0}
    assert result.artifacts == ()
    assert result.toolset[0]["version"] == "2.0.0"
    assert tools.version_calls == [OPENGREP]


def test_a_file_git_cannot_read_as_text_is_skipped() -> None:
    class Binary(FakeGit):
        def read_file(self, dest: Path, ref: str, path: str) -> str | None:
            if path == "src/b.py":
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
            return super().read_file(dest, ref, path)

    base = Binary(
        analysis=AnalysisScript(name_status={("b1", "h1"): CHANGES}),
        files=SOURCES,
        listings={("b1", "rules/"): list(RULES)},
    )
    _, tools, _ = collect(git=base)
    assert tools.calls[0]["args"][-1] == "files/src/a.py"


def test_a_file_missing_at_a_ref_is_skipped() -> None:
    files = {k: v for k, v in SOURCES.items() if k != ("h1", "src/c.py")}
    _, tools, _ = collect(git=fake_git(files=files))
    assert tools.calls[1]["args"][-1] == "files/src/a.py"


@pytest.mark.parametrize("missing", ["scratch", "base", "head"])
def test_nothing_to_read_gives_an_empty_result(missing: str) -> None:
    prepared = inputs(scratch=None if missing == "scratch" else SCRATCH)
    if missing in ("base", "head"):
        prepared = replace(prepared, analysis=prepared.analysis.model_copy(update={missing: None}))
    result, tools, _ = collect(prepared=prepared)
    assert (result.counts, result.words, result.artifacts, result.toolset) == ((), {}, (), ())
    assert tools.calls == []


def test_a_copied_file_is_scanned_at_base_under_its_source_path_without_a_rename() -> None:
    changes = (NameStatus("C", "src/c.py", "src/b.py"),)
    git = fake_git(changes, {**SOURCES, ("h1", "src/c.py"): "b"})
    base = sarif([hit("r2", "src/b.py")], [R2])
    head = sarif([hit("r2", "src/c.py")], [R2])
    result, tools, _ = collect(git=git, base=base, head=head)
    assert tools.calls[0]["args"][-1] == "files/src/b.py"
    assert table(result, BUG) == {"high": 0, "medium": 1, "low": 0, "fixed": 1, "unchanged": 0}
