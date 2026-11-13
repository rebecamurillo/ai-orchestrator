"""Parsing Opengrep SARIF, matching new against fixed, the stored baseline (epic 6 story 2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.analysis.findings_sarif import (
    Finding,
    SarifUnreadable,
    match,
    parse_findings,
    with_baseline,
)

SECOND = 2
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis" / "tier2" / "opengrep"


def digest(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def sarif(
    results: list[dict[str, Any]],
    rules: list[dict[str, Any]] | None = None,
    name: str = "Opengrep",
) -> str:
    run = {"tool": {"driver": {"name": name, "rules": rules or []}}, "results": results}
    return json.dumps({"version": "2.1.0", "runs": [run]})


def result(rule: str = "r1", uri: str = "src/a.py", **extra: Any) -> dict[str, Any]:
    region = extra.pop("region", {"startLine": 1})
    location = {"physicalLocation": {"artifactLocation": {"uri": uri}, "region": region}}
    return {"ruleId": rule, "locations": [location], **extra}


def read_from(files: dict[str, str]) -> Any:
    return files.get


def parse(text: str, files: dict[str, str] | None = None, **kw: Any) -> list[Finding]:
    return parse_findings(
        text,
        root=kw.pop("root", "/s"),
        read_source=read_from(files or {}),
        renames=kw.pop("renames", {}),
    )


def test_a_result_is_read_with_driver_name_rule_path_line_and_hash() -> None:
    text = sarif([result(uri="files/src/a.py", region={"startLine": 2})], [{"id": "r1"}])
    (found,) = parse(text, {"src/a.py": "x\n  a   b\ny"})
    assert (found.tool, found.rule_id, found.path, found.line) == ("Opengrep", "r1", "src/a.py", 2)
    assert found.text_hash == digest("a b")


@pytest.mark.parametrize("uri", ["file:///s/src/a.py", "/s/src/a.py", "files/src/a.py", "src/a.py"])
def test_the_uri_loses_its_scheme_root_and_files_prefix(uri: str) -> None:
    (found,) = parse(sarif([result(uri=uri)]), root="/s")
    assert found.path == "src/a.py"


def test_the_matched_text_is_sliced_by_columns_exclusive_at_the_end() -> None:
    region = {"startLine": 1, "startColumn": 8, "endColumn": 12}
    (found,) = parse(sarif([result(region=region)]), {"src/a.py": "return eval(x)"})
    assert found.text_hash == digest("eval")


def test_a_multi_line_region_slices_the_first_and_last_lines_by_column() -> None:
    region = {"startLine": 1, "startColumn": 3, "endLine": 3, "endColumn": 3}
    source = "abcd\nmiddle\nwxyz"
    (found,) = parse(sarif([result(region=region)]), {"src/a.py": source})
    assert found.text_hash == digest("cd middle wx")


def test_a_region_without_columns_is_whole_lines() -> None:
    region = {"startLine": 1, "endLine": 2}
    (found,) = parse(sarif([result(region=region)]), {"src/a.py": "one\ntwo\nthree"})
    assert found.text_hash == digest("one two")


def test_a_region_with_only_a_start_column_runs_to_the_end_of_its_line() -> None:
    region = {"startLine": 1, "startColumn": 3}
    (found,) = parse(sarif([result(region=region)]), {"src/a.py": "abcd\nz"})
    assert found.text_hash == digest("cd")


def test_the_snippet_stands_in_when_the_source_is_not_readable() -> None:
    region = {"startLine": 1, "snippet": {"text": " a  b "}}
    (found,) = parse(sarif([result(region=region)]))
    assert found.text_hash == digest("a b")


def test_no_source_and_no_snippet_hashes_the_empty_text() -> None:
    (found,) = parse(sarif([result()]))
    assert found.text_hash == digest("")


def test_a_line_past_the_end_of_the_file_hashes_the_empty_text() -> None:
    (found,) = parse(sarif([result(region={"startLine": 9})]), {"src/a.py": "one"})
    assert found.text_hash == digest("")


def test_the_path_is_mapped_through_renames_but_the_source_is_read_at_the_old_one() -> None:
    (found,) = parse(
        sarif([result(uri="src/b.py")]), {"src/b.py": "q"}, renames={"src/b.py": "src/c.py"}
    )
    assert found.path == "src/c.py"
    assert found.text_hash == digest("q")


def test_the_end_line_defaults_to_the_start_line() -> None:
    (found,) = parse(sarif([result(region={"startLine": 2})]), {"src/a.py": "one\ntwo\nthree"})
    assert found.text_hash == digest("two")


def test_the_rule_is_found_by_index_then_by_id() -> None:
    rules = [{"id": "other"}, {"id": "r1", "properties": {"tags": ["security", "CWE-79: X"]}}]
    by_index = parse(sarif([result("r1", ruleIndex=1)], rules))
    by_id = parse(sarif([result("r1")], rules))
    assert by_index[0].kind == by_id[0].kind == "security"
    assert by_index[0].cwe == ("CWE-79",)


def test_a_rule_index_out_of_range_falls_back_to_the_id() -> None:
    (found,) = parse(
        sarif([result("r1", ruleIndex=7)], [{"id": "r1", "properties": {"tags": ["security"]}}])
    )
    assert found.kind == "security"


def test_a_result_without_a_rule_descriptor_is_a_bug_at_warning() -> None:
    (found,) = parse(sarif([result("nope")]))
    assert (found.kind, found.severity, found.cwe) == ("bug", "medium", ())


@pytest.mark.parametrize(
    ("level", "default", "score", "expected"),
    [
        ("error", None, None, "high"),
        ("warning", None, None, "medium"),
        ("note", None, None, "low"),
        ("none", None, None, "low"),
        (None, "error", None, "high"),
        (None, None, None, "medium"),
        ("note", None, "8.1", "high"),
        ("error", None, "7.0", "high"),
        ("error", None, "6.9", "medium"),
        ("error", None, "4.0", "medium"),
        ("error", None, "3.9", "low"),
        ("note", None, "not a number", "low"),
        ("error", None, 9.5, "high"),
    ],
)
def test_severity_comes_from_the_score_else_the_level_else_the_rule_default(
    level: str | None, default: str | None, score: object, expected: str
) -> None:
    rule: dict[str, Any] = {"id": "r1", "properties": {}}
    if default:
        rule["defaultConfiguration"] = {"level": default}
    if score is not None:
        rule["properties"]["security-severity"] = score
    extra = {"level": level} if level else {}
    (found,) = parse(sarif([result("r1", **extra)], [rule]))
    assert found.severity == expected


def test_security_is_a_tag_case_insensitively_and_cwe_ids_are_unique_in_order() -> None:
    tags = ["Security", "CWE-79: A", "CWE-20: B", "CWE-79: A"]
    (found,) = parse(sarif([result("r1")], [{"id": "r1", "properties": {"tags": tags}}]))
    assert (found.kind, found.cwe) == ("security", ("CWE-79", "CWE-20"))


def test_a_rule_without_a_security_tag_is_a_bug() -> None:
    (found,) = parse(sarif([result("r1")], [{"id": "r1", "properties": {"tags": ["CWE-1"]}}]))
    assert found.kind == "bug"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        json.dumps({"runs": [{"tool": {"driver": {}}, "results": [{"ruleId": "a"}]}]}),
        json.dumps(
            {
                "runs": [
                    {
                        "tool": {"driver": {"name": "o"}},
                        "results": [{"ruleId": "a", "locations": [1]}],
                    }
                ]
            }
        ),
        json.dumps({"runs": [None]}),
        json.dumps(
            {
                "runs": [
                    {
                        "tool": {"driver": {"name": "o"}},
                        "results": [
                            {
                                "ruleId": "a",
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": "a"},
                                            "region": {"startLine": "x"},
                                        }
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
    ],
)
def test_unreadable_input_raises(text: str) -> None:
    with pytest.raises(SarifUnreadable):
        parse(text)


def finding(rule: str, path: str, text: str, **kw: Any) -> Finding:
    values: dict[str, Any] = {
        "tool": "Opengrep",
        "rule_id": rule,
        "path": path,
        "line": 1,
        "text_hash": digest(text),
        "severity": "medium",
        "kind": "bug",
        "cwe": (),
        "run_index": 0,
        "result_index": 0,
    }
    values.update(kw)
    return Finding(**values)


def test_a_moved_match_is_unchanged_a_new_one_new_and_a_gone_one_absent() -> None:
    base = [finding("r1", "src/a.py", "a", line=3), finding("r2", "src/b.py", "b")]
    head = [finding("r1", "src/a.py", "a", line=23), finding("r3", "src/c.py", "c")]
    matched = match(base, head)
    assert [f.rule_id for f in matched.new] == ["r3"]
    assert [f.rule_id for f in matched.unchanged] == ["r1"]
    assert [f.rule_id for f in matched.absent] == ["r2"]


def test_matching_counts_multiplicity() -> None:
    base = [finding("r1", "a", "t")]
    head = [finding("r1", "a", "t", line=1), finding("r1", "a", "t", line=2)]
    matched = match(base, head)
    assert (len(matched.unchanged), len(matched.new), len(matched.absent)) == (1, 1, 0)
    assert matched.new[0].line == SECOND
    gone = match(head, base)
    assert (len(gone.unchanged), len(gone.new), len(gone.absent)) == (1, 0, 1)
    assert gone.absent[0].line == SECOND


def test_a_rename_mapped_path_matches() -> None:
    base = parse(
        sarif([result("r1", uri="src/b.py")]), {"src/b.py": "x"}, renames={"src/b.py": "src/c.py"}
    )
    head = parse(sarif([result("r1", uri="src/c.py")]), {"src/c.py": "x"})
    matched = match(base, head)
    assert (len(matched.unchanged), len(matched.new), len(matched.absent)) == (1, 0, 0)


def test_the_recorded_fixtures_give_one_new_one_fixed_and_two_unchanged() -> None:
    def side(name: str, renames: dict[str, str]) -> list[Finding]:
        text = (FIXTURES / f"{name}.sarif").read_text()
        return parse_findings(
            text,
            root=str(FIXTURES),
            renames=renames,
            read_source=lambda p: (
                (FIXTURES / name / p).read_text() if (FIXTURES / name / p).exists() else None
            ),
        )

    base = side("base", {"src/e.py": "src/f.py"})
    head = side("head", {})
    matched = match(base, head)
    assert sorted(f.path for f in matched.new) == ["src/c.py"]
    assert sorted(f.path for f in matched.absent) == ["src/b.py"]
    assert sorted(f.path for f in matched.unchanged) == ["src/a.py", "src/f.py"]
    assert {f.kind for f in head} == {"security", "bug"}
    assert {f.severity for f in head} == {"high", "medium", "low"}
    assert [f.cwe for f in head if f.rule_id.endswith("os-system")] == [("CWE-78",)]


def test_every_result_of_the_stored_sarif_carries_its_baseline_state_and_no_scratch_path() -> None:
    rule_a = {"id": "r1", "properties": {"tags": ["security"]}}
    rule_b = {"id": "r2"}
    base_text = sarif(
        [
            result("r1", uri="file:///s/files/src/a.py", ruleIndex=0),
            result("r2", uri="file:///s/files/src/b.py", ruleIndex=1),
        ],
        [rule_a, rule_b],
    )
    head_text = sarif(
        [
            result("r1", uri="file:///s/files/src/a.py", ruleIndex=0),
            result("r3", uri="files/src/c.py"),
        ],
        [rule_a],
    )
    base = parse(base_text, root="/s")
    head = parse(head_text, root="/s")
    matched = match(base, head)
    stored = json.loads(with_baseline(head_text, base_text, matched, root="/s"))
    assert stored["version"] == "2.1.0"
    results = stored["runs"][0]["results"]
    states = {r["ruleId"]: r["baselineState"] for r in results}
    assert states == {"r1": "unchanged", "r3": "new", "r2": "absent"}
    uris = [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results]
    assert uris == ["src/a.py", "src/c.py", "src/b.py"]
    assert "ruleIndex" not in results[2]
    ids = [r["id"] for r in stored["runs"][0]["tool"]["driver"]["rules"]]
    assert ids == ["r1", "r2"]
    assert "/s" not in json.dumps(stored)


def test_an_absent_result_of_a_tool_without_a_head_run_gets_its_own_run() -> None:
    base_text = sarif([result("r2")], [{"id": "r2"}], name="Other")
    head_text = sarif([result("r1")], [{"id": "r1"}])
    matched = match(parse(base_text), parse(head_text))
    stored = json.loads(with_baseline(head_text, base_text, matched, root="/s"))
    assert [run["tool"]["driver"]["name"] for run in stored["runs"]] == ["Opengrep", "Other"]
    assert stored["runs"][1]["results"][0]["baselineState"] == "absent"


def test_an_absent_result_whose_rule_is_already_listed_is_not_listed_twice() -> None:
    base_text = sarif([result("r1", uri="a")], [{"id": "r1"}])
    head_text = sarif([], [{"id": "r1"}])
    matched = match(parse(base_text), parse(head_text))
    stored = json.loads(with_baseline(head_text, base_text, matched, root="/s"))
    assert len(stored["runs"][0]["tool"]["driver"]["rules"]) == 1


def test_an_absent_result_without_a_listed_descriptor_adds_none() -> None:
    base_text = sarif([result("ghost")])
    head_text = sarif([])
    matched = match(parse(base_text), parse(head_text))
    stored = json.loads(with_baseline(head_text, base_text, matched, root="/s"))
    assert stored["runs"][0]["tool"]["driver"]["rules"] == []


def test_baseline_with_only_base_marks_every_result_absent() -> None:
    base_text = sarif([result("r1")], [{"id": "r1"}])
    matched = match(parse(base_text), [])
    stored = json.loads(with_baseline(None, base_text, matched, root="/s"))
    assert [r["baselineState"] for r in stored["runs"][0]["results"]] == ["absent"]
    assert stored["version"] == "2.1.0"


def test_baseline_with_only_head_marks_every_result_new() -> None:
    head_text = sarif([result("r1")], [{"id": "r1"}])
    matched = match([], parse(head_text))
    stored = json.loads(with_baseline(head_text, None, matched, root="/s"))
    assert [r["baselineState"] for r in stored["runs"][0]["results"]] == ["new"]
