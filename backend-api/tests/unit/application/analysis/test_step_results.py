"""Tier 3 importers and collection over the Git port (epic 6 story 3, AC3-AC6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.step_results import (
    collect_step_results,
    import_coverage,
    import_junit,
    import_sarif,
    matching_files,
    sniff,
)
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.tier2_reports import ReportUnreadable
from orchestrator.application.templates.step_metric_model import StepMetric
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.catalogue import CatalogueEntry, CatalogueMethod
from orchestrator.domain.ports.git_analysis import NameStatus
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript

SCRATCH = Path("/work/analysis/1/root")
ID = "step.bench-v1.heldout_tests"
EIGHTEEN, TWO, THIRTY, FORTY = 18, 2, 30, 40


def junit(passed: int, failed: int = 0, errored: int = 0, skipped: int = 0) -> str:
    cases = [f'<testcase classname="c" name="p{i}"/>' for i in range(passed)]
    cases += [
        f'<testcase classname="c" name="f{i}"><failure message="x"/></testcase>'
        for i in range(failed)
    ]
    cases += [
        f'<testcase classname="c" name="e{i}"><error message="x"/></testcase>'
        for i in range(errored)
    ]
    cases += [f'<testcase classname="c" name="s{i}"><skipped/></testcase>' for i in range(skipped)]
    return f'<testsuite name="s">{"".join(cases)}</testsuite>'


def cobertura(covered: int, total: int) -> str:
    lines = "".join(
        f'<line number="{n}" hits="{1 if n <= covered else 0}"/>' for n in range(1, total + 1)
    )
    cls = f'<class filename="a.py"><lines>{lines}</lines></class>'
    return f"<coverage><packages><package><classes>{cls}</classes></package></packages></coverage>"


def jacoco(covered: int, total: int) -> str:
    lines = "".join(
        f'<line nr="{n}" mi="0" ci="{1 if n <= covered else 0}"/>' for n in range(1, total + 1)
    )
    source = f'<sourcefile name="A.java">{lines}</sourcefile>'
    return f'<report name="r"><package name="p">{source}</package></report>'


def sarif(*levels: str | None) -> str:
    results = [{"ruleId": "r"} if level is None else {"level": level} for level in levels]
    return json.dumps({"version": "2.1.0", "runs": [{"results": results}]})


def metric(fmt: str = "junit", path: str = "out/heldout.xml", metric_id: str = ID) -> StepMetric:
    entry = CatalogueEntry(
        metric_id,
        "label",
        "step",
        "A",
        ("run",),
        "tests",
        "report",
        None,
        False,
        (),
        None,
        False,
        (CatalogueMethod(1, "reads it", {}),),
    )
    return StepMetric(line=1, entry=entry, format=fmt, path=path)  # type: ignore[arg-type]


def analysis(path: str = ".", status: str = "ok") -> Analysis:
    return Analysis(
        id=UUID(int=5),
        run_id=UUID(int=1),
        repository_path=path,
        base="b1",
        head="h1",
        status=status,  # type: ignore[arg-type]
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
    )


def prepared(
    path: str = ".", status: str = "ok", *, scratch: Path | None = SCRATCH
) -> RepositoryInputs:
    return RepositoryInputs(analysis(path, status), scratch, DEFAULT_DECLARATION, (), False)


def git(files: dict[str, str], changed: tuple[str, ...] = (), status: str = "A") -> FakeGit:
    listing: dict[tuple[str, str], list[str]] = {}
    for path in files:
        parent = str(Path(path).parent)
        listing.setdefault(("h1", parent), []).append(path)
        listing.setdefault(("h1", "."), []).append(path)
    script = AnalysisScript(
        name_status={("b1", "h1"): tuple(NameStatus(status, p, None) for p in changed)}  # type: ignore[arg-type]
    )
    return FakeGit(
        analysis=script, files={("h1", p): t for p, t in files.items()}, listings=listing
    )


# --- importers -----------------------------------------------------------------------------


def test_junit_counts_every_outcome_across_files() -> None:
    counts = import_junit([junit(EIGHTEEN, TWO), junit(1, 0, 3, 4)])

    assert counts == {"passed": 19, "failed": TWO, "errored": 3, "skipped": 4}


def test_junit_with_no_cases_has_every_source_at_zero() -> None:
    assert import_junit(["<testsuite/>"]) == {"passed": 0, "failed": 0, "errored": 0, "skipped": 0}


@pytest.mark.parametrize("build", [cobertura, jacoco])
def test_coverage_counts_covered_and_instrumented_lines(build) -> None:  # type: ignore[no-untyped-def]
    assert import_coverage([build(THIRTY, FORTY)]) == {"covered": THIRTY, "instrumented": FORTY}


def test_coverage_sums_files() -> None:
    assert import_coverage([cobertura(1, 2), jacoco(3, 4)]) == {"covered": 4, "instrumented": 6}


def test_sarif_counts_by_level_and_defaults_to_warning() -> None:
    counts = import_sarif([sarif("error", "error", "warning", None)])

    assert counts == {"error": 2, "warning": 2, "note": 0, "none": 0}


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        json.dumps({"runs": {}}),
        json.dumps({"runs": [5]}),
        json.dumps({"runs": [{"results": "x"}]}),
        json.dumps({"runs": [{"results": [5]}]}),
        json.dumps({"runs": [{"results": [{"level": "fatal"}]}]}),
    ],
)
def test_a_malformed_sarif_document_is_unreadable(text: str) -> None:
    with pytest.raises(ReportUnreadable):
        import_sarif([text])


def test_a_sarif_run_without_results_counts_nothing() -> None:
    assert import_sarif([json.dumps({"runs": [{}]})]) == dict.fromkeys(
        ("error", "warning", "note", "none"), 0
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (junit(1), "junit"),
        ("<testsuites/>", "junit"),
        (cobertura(1, 1), "cobertura"),
        (jacoco(1, 1), "jacoco"),
        (sarif("error"), "sarif"),
        ("<other/>", None),
        ("<broken", None),
        ("<!DOCTYPE x><testsuite/>", None),
        ("{nope", None),
        (json.dumps({"runs": [], "version": 2}), None),
        (json.dumps({"hello": 1}), None),
        ("plain text", None),
    ],
)
def test_sniff_names_the_format_or_nothing(text: str, expected: str | None) -> None:
    assert sniff(text) == expected


# --- matching -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("glob", "prefix"),
    [
        ("out/heldout.xml", "out"),
        ("out/*/r.xml", "out"),
        ("a/b/**/r.xml", "a/b"),
        ("**/r.xml", "."),
        ("r.xml", "."),
    ],
)
def test_the_listing_is_asked_for_the_literal_directory_prefix(glob: str, prefix: str) -> None:
    fake = git({})

    matching_files(fake, SCRATCH, "h1", glob)

    assert fake.calls[-1][1] == (SCRATCH, "h1", prefix)


def test_a_glob_selects_only_the_paths_it_matches() -> None:
    fake = git({"out/a/r.xml": "x", "out/b/r.xml": "x", "out/b/s.xml": "x"})
    fake.listings[("h1", "out")] = ["out/a/r.xml", "out/b/r.xml", "out/b/s.xml"]

    assert matching_files(fake, SCRATCH, "h1", "out/*/r.xml") == ["out/a/r.xml", "out/b/r.xml"]


# --- collection ---------------------------------------------------------------------------


def test_a_declared_junit_file_at_head_yields_its_counts() -> None:
    fake = git({"out/heldout.xml": junit(EIGHTEEN, TWO)})

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert {(c.metric_id, c.source, c.value) for c in found.counts} == {
        (ID, "passed", EIGHTEEN),
        (ID, "failed", TWO),
        (ID, "errored", 0),
        (ID, "skipped", 0),
    }
    assert all(isinstance(c, Count) and c.rate is None for c in found.counts)
    assert dict(found.words) == {}
    assert found.not_catalogued == ()


def test_a_glob_matching_two_files_sums_them() -> None:
    fake = git({"out/a.xml": junit(1), "out/b.xml": junit(2)})

    found = collect_step_results(prepared(), git=fake, declared=[metric(path="out/*.xml")])

    assert {c.source: c.value for c in found.counts}["passed"] == 3  # noqa: PLR2004


def test_no_file_matching_is_a_word_and_no_figure() -> None:
    found = collect_step_results(prepared(), git=git({}), declared=[metric()])

    assert found.counts == ()
    assert dict(found.words) == {ID: "n/a — no file matches out/heldout.xml"}


def test_an_unreadable_file_is_a_not_run_word() -> None:
    fake = git({"out/heldout.xml": "<broken"})

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert found.counts == ()
    assert dict(found.words)[ID].startswith("not run — junit report unreadable: ")


def test_a_file_missing_between_listing_and_read_is_unreadable() -> None:
    fake = git({})
    fake.listings[("h1", "out")] = ["out/heldout.xml"]

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert dict(found.words)[ID].startswith("not run — junit report unreadable")


def test_a_dtd_is_refused() -> None:
    fake = git({"out/heldout.xml": '<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>'})

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert "document type declarations are refused" in dict(found.words)[ID]


def test_an_error_without_text_is_named_by_its_class() -> None:
    fake = git({"out/s.sarif": ""})
    fake.listings[("h1", "out")] = ["out/s.sarif"]

    found = collect_step_results(prepared(), git=fake, declared=[metric("sarif", "out/s.sarif")])

    assert dict(found.words)[ID].startswith("not run — sarif report unreadable: ")


def test_a_file_no_declaration_claims_is_not_catalogued() -> None:
    fake = git(
        {"out/heldout.xml": junit(1), "out/other.xml": junit(1)},
        changed=("out/heldout.xml", "out/other.xml"),
    )

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert found.not_catalogued == ("out/other.xml",)
    assert {c.metric_id for c in found.counts} == {ID}


def test_not_catalogued_is_sorted_and_only_for_reports() -> None:
    files = {
        "z.sarif": sarif("error"),
        "a/cov.xml": cobertura(1, 1),
        "notes.xml": "<other/>",
        "data.json": json.dumps({"a": 1}),
        "readme.md": junit(1),
    }
    fake = git(files, changed=tuple(files))

    found = collect_step_results(prepared(), git=fake, declared=[])

    assert found.not_catalogued == ("a/cov.xml", "z.sarif")


def test_a_deleted_or_unreadable_changed_file_is_not_listed() -> None:
    fake = git({"x.xml": junit(1)}, changed=("x.xml", "gone.xml"), status="D")
    assert collect_step_results(prepared(), git=fake, declared=[]).not_catalogued == ()

    fake = git({}, changed=("gone.xml",), status="M")
    assert collect_step_results(prepared(), git=fake, declared=[]).not_catalogued == ()


def test_a_member_repository_is_ignored() -> None:
    fake = git({"out/heldout.xml": junit(1)}, changed=("out/heldout.xml",))

    found = collect_step_results(prepared("hub/member"), git=fake, declared=[metric()])

    assert found.counts == () and dict(found.words) == {} and found.not_catalogued == ()
    assert fake.calls == []


@pytest.mark.parametrize("case", ["failed", "no scratch", "no base", "no head"])
def test_a_failed_or_unprepared_analysis_makes_no_git_call(case: str) -> None:
    fake = git({"out/heldout.xml": junit(1)})
    inputs = prepared(
        status="failed" if case == "failed" else "ok",
        scratch=None if case == "no scratch" else SCRATCH,
    )
    if case in ("no base", "no head"):
        stripped = inputs.analysis.model_copy(
            update={"base" if case == "no base" else "head": None}
        )
        inputs = RepositoryInputs(stripped, SCRATCH, DEFAULT_DECLARATION, (), False)

    found = collect_step_results(inputs, git=fake, declared=[metric()])

    assert found.counts == () and found.not_catalogued == ()
    assert fake.calls == []


# --- untrusted report files never fail the repository's analysis ---------------------------

DEEP_JSON = "[" * 100_000


def _undecodable(dest: Path, ref: str, path: str) -> str | None:
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def test_deeply_nested_json_is_sniffed_as_nothing() -> None:
    assert sniff(DEEP_JSON) is None


def test_deeply_nested_json_at_a_declared_path_is_a_not_run_word() -> None:
    fake = git({"out/s.sarif": DEEP_JSON})

    found = collect_step_results(prepared(), git=fake, declared=[metric("sarif", "out/s.sarif")])

    assert found.counts == ()
    assert dict(found.words)[ID].startswith("not run — sarif report unreadable: not JSON")


def test_a_declared_file_that_is_not_utf8_is_a_not_run_word() -> None:
    fake = git({"out/heldout.xml": junit(1)})
    fake.read_file = _undecodable  # type: ignore[method-assign]

    found = collect_step_results(prepared(), git=fake, declared=[metric()])

    assert found.counts == ()
    assert dict(found.words)[ID].startswith("not run — junit report unreadable: ")


def test_a_changed_file_that_is_not_utf8_or_too_deep_is_not_listed() -> None:
    fake = git({"deep.json": DEEP_JSON, "ok.xml": junit(1)}, changed=("deep.json", "ok.xml"))
    assert collect_step_results(prepared(), git=fake, declared=[]).not_catalogued == ("ok.xml",)

    fake = git({"bin.xml": junit(1)}, changed=("bin.xml",))
    fake.read_file = _undecodable  # type: ignore[method-assign]
    assert collect_step_results(prepared(), git=fake, declared=[]).not_catalogued == ()
