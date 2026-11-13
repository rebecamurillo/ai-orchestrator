"""Tier 1b: duplication and function complexity over the change (epic 5 story 3, AC5 and AC6).

The jscpd and lizard outputs are the ones recorded in `fixtures/analysis/tier1b/` (see its
README); lizard's `file` column holds the folder it was recorded in, which is re-pointed here
at the scratch folder the code scans.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.duplication import duplication_added, relative_sarif
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.secrets import SARIF_MEDIA_TYPE
from orchestrator.application.analysis.tier1b import (
    COGNITIVE,
    CYCLOMATIC,
    DUPLICATION,
    JSCPD,
    JSCPD_COMMAND,
    LIZARD,
    LIZARD_COGNITIVE_COMMAND,
    LIZARD_COMMAND,
    NOT_COVERED,
    FunctionRow,
    Tier1bResult,
    collect_tier1b,
    functions_over,
    parse_lizard,
)
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.git_analysis import NameStatus
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.package_lookup import FakePackageLookup
from tests.unit.fakes.workspace import FakeWorkspace

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis" / "tier1b"
ROOT = Path("/work/analysis")
ANALYSIS = UUID(int=5)
RELATIVE = f"{ANALYSIS}/root"
CLONE = ROOT / RELATIVE
HEAD_FILES = f"{CLONE}.head/files/"
NOW = datetime(2026, 11, 13, tzinfo=UTC)
NOTHING_ADDED = "diff --git a/x b/x\n"


def text(name: str) -> str:
    return (FIXTURES / name).read_text()


def prepared() -> RepositoryInputs:
    analysis = Analysis(
        id=ANALYSIS,
        run_id=UUID(int=1),
        calculation_id=UUID(int=2),
        repository_path=".",
        base="b1",
        head="h1",
        status="ok",
        created_at=NOW,
    )
    return RepositoryInputs(analysis, CLONE, DEFAULT_DECLARATION, (), False)


def added_diff(**numbers: list[int]) -> str:
    """A zero-context diff adding single lines at the given head line numbers of each file."""
    out = []
    for path, lines in numbers.items():
        name = re.sub(r"_(py|ts|hs)$", r".\1", path).replace("__", "/")
        out.append(f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n")
        out += [f"@@ -0,0 +{line} @@\n+x\n" for line in lines]
    return "".join(out)


def run(  # noqa: PLR0913 — the scripted world of one collection
    files: dict[str, str],
    diff: str = NOTHING_ADDED,
    runs: dict[str, ToolRun] | None = None,
    workspace: FakeWorkspace | None = None,
    *,
    lookups: bool = True,
    statuses: str = "A",
) -> tuple[Tier1bResult, FakeAnalysisTools, FakeWorkspace]:
    workspace = workspace or FakeWorkspace()
    script = AnalysisScript(
        name_status={("b1", "h1"): tuple(NameStatus(statuses, p, None) for p in files)},  # type: ignore[misc]
        diff_text={("b1", "h1"): diff},
    )
    git = FakeGit(analysis=script, files={("h1", p): t for p, t in files.items()})
    tools = FakeAnalysisTools(runs or {}, workspace=workspace, root=ROOT)
    result = collect_tier1b(
        prepared(),
        git=git,
        scratch_root=workspace,
        tools=tools,
        lookup=FakePackageLookup(),
        lookups=lookups,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(500, 600)).__next__,
    )
    return result, tools, workspace


def jscpd_files() -> dict[str, str]:
    return {name: text(f"jscpd-input/files/{name}") for name in ("a.py", "b.py", "c.py", "d.py")}


SCAN_ROOT = f"{CLONE}.head/files"


def jscpd_sarif(name: str, folder: str) -> str:
    """A recorded SARIF, the recorder's absolute scan folder moved to this test's scan root."""
    return re.sub(rf"file://[^\"]*/{folder}/files/", f"file://{SCAN_ROOT}/", text(name))


def jscpd_workspace() -> FakeWorkspace:
    return FakeWorkspace(
        files={
            f"{RELATIVE}.jscpd/jscpd-report.json": text("jscpd-report.json"),
            f"{RELATIVE}.jscpd/jscpd-report.sarif": jscpd_sarif("jscpd-sarif.json", "jscpd-input"),
        }
    )


def lizard_text(name: str) -> str:
    return re.sub(r"[^\",@]*/lizard-input/files/", HEAD_FILES, text(name))


class LizardTools(FakeAnalysisTools):
    """Answers the cyclomatic and the cognitive lizard runs with their recorded CSV."""

    def __init__(self, workspace: FakeWorkspace, csv: str, cognitive_csv: str) -> None:
        super().__init__({}, workspace=workspace, root=ROOT)
        self._csv = {False: csv, True: cognitive_csv}

    def run(self, tool: str, args, cwd: Path, timeout: float) -> ToolRun:  # type: ignore[no-untyped-def]
        super().run(tool, args, cwd, timeout)
        if tool == LIZARD:
            return ToolRun(0, self._csv["-Ecognitive" in args], "", "1.26.0")
        return ToolRun(0, "", "", "5.4.3")


def collect_with_lizard(csv: str, cognitive_csv: str, diff: str, files: dict[str, str]):  # type: ignore[no-untyped-def]
    workspace = FakeWorkspace()
    script = AnalysisScript(
        name_status={("b1", "h1"): tuple(NameStatus("A", p, None) for p in files)},
        diff_text={("b1", "h1"): diff},
    )
    git = FakeGit(analysis=script, files={("h1", p): t for p, t in files.items()})
    tools = LizardTools(workspace, csv, cognitive_csv)
    result = collect_tier1b(
        prepared(),
        git=git,
        scratch_root=workspace,
        tools=tools,
        lookup=FakePackageLookup(),
        lookups=True,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(500, 600)).__next__,
    )
    return result, tools


def figure(result: Tier1bResult, metric: str, source: str | None = None) -> int:
    (found,) = [c for c in result.counts if (c.metric_id, c.source) == (metric, source)]
    return found.value


# ── duplication (AC5) ────────────────────────────────────────────────────────


def test_only_the_added_lines_inside_a_clone_are_counted_and_the_sarif_is_kept() -> None:
    diff = added_diff(a_py=[1, 5, 6], b_py=[10], c_py=[1], d_py=[2])
    runs = {JSCPD: ToolRun(0, "", "", "5.4.3")}
    result, tools, _ = run(jscpd_files(), diff, runs, jscpd_workspace())
    assert figure(result, DUPLICATION) == 3
    assert result.tool_versions[JSCPD] == "5.4.3"
    (artifact,) = [a for a in result.artifacts if a.tool == "jscpd"]
    assert artifact.media_type == SARIF_MEDIA_TYPE
    assert artifact.analysis_id == ANALYSIS
    (call,) = [c for c in tools.calls if c["tool"] == JSCPD]
    assert call["args"] == (
        "--reporters",
        "sarif,json",
        "--output",
        f"{CLONE}.jscpd",
        "files/a.py",
        "files/b.py",
        "files/c.py",
        "files/d.py",
    )
    assert call["cwd"] == Path(f"{CLONE}.head")
    assert call["timeout"] == 10
    assert JSCPD_COMMAND == ("--reporters", "sarif,json", "--output", "{dir}", "{files}")


def test_the_head_files_are_written_below_the_scanned_folder() -> None:
    _, _, workspace = run(jscpd_files(), runs={JSCPD: ToolRun(0, "", "", "5.4.3")})
    assert workspace.read(f"{RELATIVE}.head/files/a.py") == text("jscpd-input/files/a.py")


def test_the_stored_sarif_holds_no_absolute_path_or_file_uri() -> None:
    recorded = text("jscpd-sarif.json")
    assert "file:///" in recorded
    runs = {JSCPD: ToolRun(0, "", "", "5.4.3")}
    result, _, _ = run(jscpd_files(), added_diff(a_py=[5]), runs, jscpd_workspace())
    (artifact,) = [a for a in result.artifacts if a.tool == "jscpd"]
    body = artifact.body.decode()
    assert "file://" not in body
    assert "/work/" not in body
    document = json.loads(body)
    assert "originalUriBaseIds" not in document["runs"][0]
    uris = [
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in document["runs"][0]["results"]
    ]
    assert uris == ["a.py", "c.py"]


def located(artifact_location: dict[str, str]) -> dict[str, object]:
    return {"physicalLocation": {"artifactLocation": artifact_location}}


def test_file_uris_become_relative_to_the_scan_root_and_no_base_is_kept() -> None:
    """Operator ruling 2026-11-13 (replaces the `./` base rewrite): every `file://` location,
    with or without a base id, becomes its path below the scan root; one outside it keeps its
    file name only."""
    document = {
        "runs": [
            {
                "originalUriBaseIds": {
                    "%SRCROOT%": {"uri": "file:///scan/head/files/src/"},
                    "%OTHER%": {"uri": "file:///elsewhere/"},
                },
                "artifacts": [{"location": {"uri": "a%20b.py", "uriBaseId": "%SRCROOT%"}}],
                "results": [
                    {
                        "locations": [
                            located({"uri": "b.py", "uriBaseId": "%OTHER%"}),
                            located({"uri": "file:///scan/head/files/lib/c.py"}),
                            located({"uri": "plain.py"}),
                            located({"uri": "d.py", "uriBaseId": "%NONE%"}),
                        ],
                        "n": 3,
                    }
                ],
            }
        ]
    }
    rewritten = json.loads(relative_sarif(json.dumps(document), "/scan/head/files/"))
    run_ = rewritten["runs"][0]
    assert "originalUriBaseIds" not in run_
    assert run_["artifacts"] == [{"location": {"uri": "src/a b.py"}}]
    locations = [
        entry["physicalLocation"]["artifactLocation"] for entry in run_["results"][0]["locations"]
    ]
    assert locations == [
        {"uri": "b.py"},
        {"uri": "lib/c.py"},
        {"uri": "plain.py"},
        {"uri": "d.py", "uriBaseId": "%NONE%"},
    ]
    assert run_["results"][0]["n"] == 3


def test_no_production_file_means_no_jscpd_run_and_a_zero() -> None:
    result, tools, _ = run({"README.md": "# x\n"})
    assert figure(result, DUPLICATION) == 0
    assert [c for c in tools.calls if c["tool"] == JSCPD] == []
    assert JSCPD not in result.tool_versions
    assert [a for a in result.artifacts if a.tool == "jscpd"] == []


def test_a_jscpd_that_does_not_finish_reads_not_run_and_the_analysis_goes_on() -> None:
    timed_out = ToolRun(None, "", "", "5.4.3", timed_out=True)
    result, _, _ = run(jscpd_files(), runs={JSCPD: timed_out})
    assert result.words[DUPLICATION] == "not run — jscpd: timed out"
    assert result.tool_versions[JSCPD] == "5.4.3"
    failed = ToolRun(2, "boom\nmore", "", "5.4.3")
    result, _, _ = run(jscpd_files(), runs={JSCPD: failed})
    assert result.words[DUPLICATION] == "not run — jscpd: exit 2: boom"
    assert figure(result, "code.functions_over_cyclomatic", "count") == 0


def test_a_missing_or_unreadable_jscpd_sarif_reads_not_run() -> None:
    """Operator ruling 2026-11-13: the SARIF is the only source of fragment paths, so the JSON
    report alone gives no figure (replaces "a missing SARIF keeps the count")."""
    ok = {JSCPD: ToolRun(0, "", "", "5.4.3")}
    result, _, _ = run(jscpd_files(), runs=ok)
    assert result.words[DUPLICATION] == "not run — jscpd: no report"
    only_json = FakeWorkspace(
        files={f"{RELATIVE}.jscpd/jscpd-report.json": text("jscpd-report.json")}
    )
    result, _, _ = run(jscpd_files(), added_diff(a_py=[5]), ok, only_json)
    assert result.words[DUPLICATION] == "not run — jscpd: no report"
    assert [a for a in result.artifacts if a.tool == "jscpd"] == []
    for body in ("{not json", "[]", '{"runs": [{"results": [{"locations": [1]}]}]}'):
        workspace = FakeWorkspace(files={f"{RELATIVE}.jscpd/jscpd-report.sarif": body})
        result, _, _ = run(jscpd_files(), runs=ok, workspace=workspace)
        assert result.words[DUPLICATION] == "not run — jscpd: report unreadable"
        assert [a for a in result.artifacts if a.tool == "jscpd"] == []


def sarif_clone(*fragments: tuple[str, int, int]) -> dict[str, object]:
    first, *related = [
        {
            "physicalLocation": {
                "artifactLocation": {"uri": f"file:///scan/files/{path}"},
                "region": {"startLine": start, "endLine": end},
            }
        }
        for path, start, end in fragments
    ]
    return {"locations": [first], "relatedLocations": related}


def test_duplication_counts_distinct_added_lines_across_every_fragment() -> None:
    sarif = json.dumps(
        {
            "runs": [
                {
                    "results": [
                        sarif_clone(("src/a.py", 2, 4), ("src/b.py", 10, 12)),
                        sarif_clone(("src/a.py", 4, 6), ("src/b.py", 1, 1)),
                        sarif_clone(("../out.py", 1, 9)),
                        {
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "file:///elsewhere/a.py"},
                                        "region": {"startLine": 1, "endLine": 9},
                                    }
                                },
                                {"physicalLocation": {"artifactLocation": {"index": 0}}},
                            ]
                        },
                    ]
                }
            ]
        }
    )
    added = {
        "src/a.py": frozenset({1, 2, 4, 6, 7}),
        "src/b.py": frozenset({11, 1}),
        "out.py": frozenset({1}),
    }
    assert duplication_added(sarif, added, "/scan/files") == 5  # a: 2, 4, 6; b: 11, 1
    assert duplication_added('{"runs": []}', added, "/scan/files") == 0


# ── function complexity (AC6) ────────────────────────────────────────────────


def test_a_changed_function_over_the_threshold_is_counted_and_an_unchanged_one_is_not() -> None:
    files = {"a.py": text("lizard-input/files/a.py"), "b.ts": text("lizard-input/files/b.ts")}
    result, tools = collect_with_lizard(
        lizard_text("lizard.csv"),
        lizard_text("lizard-cognitive.csv"),
        added_diff(a_py=[10]),
        files,
    )
    assert figure(result, CYCLOMATIC, "count") == 1
    assert figure(result, CYCLOMATIC, "worst") == 22
    assert figure(result, COGNITIVE, "count") == 1
    assert figure(result, COGNITIVE, "worst") == 21
    assert result.tool_versions[LIZARD] == "1.26.0"
    plain, cognitive = [c for c in tools.calls if c["tool"] == LIZARD]
    assert plain["args"] == ("--csv", f"{HEAD_FILES}a.py", f"{HEAD_FILES}b.ts")
    assert cognitive["args"] == ("--csv", "-Ecognitive", f"{HEAD_FILES}a.py", f"{HEAD_FILES}b.ts")
    assert plain["cwd"] == cognitive["cwd"] == CLONE.parent
    assert plain["timeout"] == cognitive["timeout"] == 10
    assert LIZARD_COMMAND == ("--csv", "{files}")
    assert LIZARD_COGNITIVE_COMMAND == ("--csv", "-Ecognitive", "{files}")


def test_the_worst_and_the_count_are_zero_when_no_changed_function_is_over() -> None:
    files = {"a.py": text("lizard-input/files/a.py"), "b.ts": text("lizard-input/files/b.ts")}
    result, _ = collect_with_lizard(
        lizard_text("lizard.csv"), lizard_text("lizard-cognitive.csv"), added_diff(b_ts=[2]), files
    )
    assert figure(result, CYCLOMATIC, "count") == 0
    assert figure(result, CYCLOMATIC, "worst") == 0
    by_source = {c.source: c for c in result.counts if c.metric_id == CYCLOMATIC}
    assert (by_source["count"].combine, by_source["worst"].combine) == ("sum", "max")
    assert by_source["count"].rate is None


def test_a_language_lizard_gives_no_cognitive_value_for_reads_not_covered() -> None:
    files = {"c.hs": "pick a b = a\n"}
    result, _ = collect_with_lizard("", "", added_diff(c_hs=[1]), files)
    assert result.words[COGNITIVE] == NOT_COVERED == "n/a — language not covered"
    assert figure(result, CYCLOMATIC, "count") == 0


def test_a_lizard_that_does_not_finish_reads_not_run_for_that_run_alone() -> None:
    timed_out = ToolRun(None, "", "", "1.26.0", timed_out=True)
    result, _, _ = run({"a.py": "x = 1\n"}, runs={LIZARD: timed_out})
    assert result.words[CYCLOMATIC] == "not run — lizard: timed out"
    assert result.words[COGNITIVE] == "not run — lizard: timed out"
    failed = ToolRun(1, "bad option\nmore", "", "1.26.0")
    result, _, _ = run({"a.py": "x = 1\n"}, runs={LIZARD: failed})
    assert result.words[CYCLOMATIC] == "not run — lizard: exit 1: bad option"


def test_deleted_files_are_neither_read_nor_scanned() -> None:
    result, tools, _ = run({"a.py": "x = 1\n"}, statuses="D")
    assert tools.calls == []
    assert figure(result, DUPLICATION) == 0
    assert figure(result, CYCLOMATIC, "count") == 0
    assert figure(result, COGNITIVE, "worst") == 0


def test_a_file_the_commit_does_not_hold_is_not_written() -> None:
    workspace = FakeWorkspace()
    script = AnalysisScript(name_status={("b1", "h1"): (NameStatus("A", "gone.py", None),)})
    result = collect_tier1b(
        prepared(),
        git=FakeGit(analysis=script, files={}),
        scratch_root=workspace,
        tools=FakeAnalysisTools(workspace=workspace, root=ROOT),
        lookup=FakePackageLookup(),
        lookups=True,
        now=NOW,
        new_id=lambda: UUID(int=1),
    )
    assert workspace.exists(f"{RELATIVE}.head") is False
    assert figure(result, CYCLOMATIC, "count") == 0


def test_an_analysis_with_no_scratch_clone_holds_nothing() -> None:
    inputs = RepositoryInputs(prepared().analysis, None, DEFAULT_DECLARATION, (), False)
    result = collect_tier1b(
        inputs,
        git=FakeGit(),
        scratch_root=FakeWorkspace(),
        tools=FakeAnalysisTools(),
        lookup=FakePackageLookup(),
        lookups=True,
        now=NOW,
        new_id=lambda: UUID(int=1),
    )
    assert result == Tier1bResult()


# ── the dependencies, through the same call ──────────────────────────────────


def test_the_dependency_signals_and_the_osv_version_come_with_the_tier() -> None:
    lock = text("pnpm-lock.head.yaml")
    workspace = FakeWorkspace()
    script = AnalysisScript(
        name_status={("b1", "h1"): (NameStatus("M", "pnpm-lock.yaml", None),)},
    )
    git = FakeGit(analysis=script, files={("h1", "pnpm-lock.yaml"): lock})
    lookup = FakePackageLookup()
    result = collect_tier1b(
        prepared(),
        git=git,
        scratch_root=workspace,
        tools=FakeAnalysisTools(workspace=workspace, root=ROOT),
        lookup=lookup,
        lookups=True,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(500, 600)).__next__,
    )
    assert figure(result, "code.deps_changed", "added") == 4
    assert workspace.read(f"{RELATIVE}.lock/pnpm-lock.yaml") == lock
    assert lookup.calls[-1]["lockfile_path"] == Path(f"{CLONE}.lock") / "pnpm-lock.yaml"
    assert result.tool_versions["osv-scanner"] == "0.0.0"
    assert result.lookup_date == NOW.date()
    assert result.vulnerability_db_date == NOW.date()


def test_lookups_off_reaches_the_dependency_signals() -> None:
    result, _, _ = run({"pnpm-lock.yaml": text("pnpm-lock.head.yaml")}, lookups=False)
    assert result.words["code.deps_recent"] == "not run — lookups off"
    assert result.lookup_date is None


# ── the pure helpers ─────────────────────────────────────────────────────────


def test_parse_lizard_reads_data_rows_and_skips_the_rest() -> None:
    csv_text = (
        "warning: something\n"
        '5,3,40,1,5,"f@1-5@x.py","x.py","f","f( a )",1,5,7\n'
        "1,2,3\n"
        '5,3,40,1,5,"g@1-5@x.py","x.py","g","g( a )",a,b,7\n'
        '6,4,40,1,6,"h@7-12@x.py","x.py","h","h( a )",7,12\n'
    )
    assert parse_lizard(csv_text, cognitive=True) == [FunctionRow("x.py", 1, 5, 7)]
    assert parse_lizard(csv_text, cognitive=False) == [
        FunctionRow("x.py", 1, 5, 3),
        FunctionRow("x.py", 7, 12, 4),
    ]


def test_functions_over_needs_an_added_line_inside_the_range_and_a_value_above_the_threshold() -> (
    None
):
    rows = [
        FunctionRow("a.py", 1, 10, 16),
        FunctionRow("a.py", 20, 30, 40),
        FunctionRow("a.py", 40, 50, 15),
        FunctionRow("b.py", 1, 10, 99),
    ]
    added = {"a.py": frozenset({10, 25, 45})}
    assert functions_over(rows, added, 15) == (2, 40)
    assert functions_over(rows, {}, 15) == (0, 0)


FOLDER_FILES = (
    "src/billing/invoice.py",
    "lib/report/summary.py",
    "api/helpers.py",
    "web/helpers.py",
)


def folders_run(diff: str) -> Tier1bResult:
    """jscpd 5.4.3's recorded run over files in four folders (`jscpd-folders-output/`)."""
    files = {path: text(f"jscpd-folders-input/files/{path}") for path in FOLDER_FILES}
    sarif = jscpd_sarif("jscpd-folders-output/jscpd-report.sarif", "jscpd-folders-input")
    workspace = FakeWorkspace(
        files={
            f"{RELATIVE}.jscpd/jscpd-report.sarif": sarif,
            f"{RELATIVE}.jscpd/jscpd-report.json": text("jscpd-folders-output/jscpd-report.json"),
        }
    )
    result, _, _ = run(files, diff, {JSCPD: ToolRun(0, "", "", "5.4.3")}, workspace)
    return result


def artifact_uris(result: Tier1bResult) -> set[str]:
    (artifact,) = [a for a in result.artifacts if a.tool == JSCPD]
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("uri"), str):
                found.add(value["uri"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(json.loads(artifact.body))
    return found


def test_a_clone_across_two_folders_counts_its_added_lines_at_their_relative_paths() -> None:
    """Operator ruling 2026-11-13: paths come from the SARIF, relative to the scan root; the
    recorded fragments are invoice.py 3-19 and summary.py 6-22."""
    diff = added_diff(src__billing__invoice_py=[5, 20], lib__report__summary_py=[2, 6])
    result = folders_run(diff)
    assert figure(result, DUPLICATION) == 2  # invoice.py 5, summary.py 6
    assert artifact_uris(result) == set(FOLDER_FILES)
    (artifact,) = [a for a in result.artifacts if a.tool == JSCPD]
    assert "file://" not in artifact.body.decode()
    assert SCAN_ROOT not in artifact.body.decode()


def test_two_files_with_one_basename_in_different_folders_are_told_apart() -> None:
    """Recorded fragments: api/helpers.py 3-14, web/helpers.py 7-18."""
    inside_web = folders_run(added_diff(api__helpers_py=[1], web__helpers_py=[8]))
    assert figure(inside_web, DUPLICATION) == 1
    # web/helpers.py line 4 lies inside api's fragment, not web's: a basename would count it.
    outside = folders_run(added_diff(api__helpers_py=[2], web__helpers_py=[4]))
    assert figure(outside, DUPLICATION) == 0


def test_the_recorded_folder_run_names_fragments_by_basename_in_its_json_only() -> None:
    """Why the JSON `name` is never read: jscpd 5.4.3 gives the bare basename there."""
    report = json.loads(text("jscpd-folders-output/jscpd-report.json"))
    names = {
        clone[side]["name"]
        for clone in report["duplicates"]
        for side in ("firstFile", "secondFile")
    }
    assert names == {"helpers.py", "summary.py", "invoice.py"}
    sarif = text("jscpd-folders-output/jscpd-report.sarif")
    root = str(FIXTURES / "jscpd-folders-input" / "files")
    moved = sarif.replace(
        re.search(r"file://([^\"]*/jscpd-folders-input/files)/", sarif).group(1),  # type: ignore[union-attr]
        root,
    )
    added = {"api/helpers.py": frozenset({3}), "web/helpers.py": frozenset({3})}
    assert duplication_added(moved, added, root) == 1


class BinaryGit(FakeGit):
    """A head file git cannot hand back as text, as the subprocess adapter fails on an image."""

    def read_file(self, dest: Path, ref: str, path: str) -> str | None:
        if path.endswith(".png"):
            raise UnicodeDecodeError("utf-8", b"\x89", 0, 1, "invalid start byte")
        return super().read_file(dest, ref, path)


def test_a_changed_binary_file_is_skipped_not_a_crash() -> None:
    workspace = FakeWorkspace()
    script = AnalysisScript(
        name_status={("b1", "h1"): (NameStatus("A", "logo.png", None),)},
        diff_text={("b1", "h1"): NOTHING_ADDED},
    )
    result = collect_tier1b(
        prepared(),
        git=BinaryGit(analysis=script, files={}),
        scratch_root=workspace,
        tools=FakeAnalysisTools({}, workspace=workspace, root=ROOT),
        lookup=FakePackageLookup(),
        lookups=True,
        now=NOW,
        new_id=iter(UUID(int=n) for n in range(500, 600)).__next__,
    )
    assert figure(result, CYCLOMATIC, "count") == 0
    assert figure(result, DUPLICATION) == 0
