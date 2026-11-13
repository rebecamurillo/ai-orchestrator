"""Tier 1a counts over unified diffs (story 5.2, AC1, AC2, AC5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION, Declaration
from orchestrator.application.analysis.tier1a import (
    ROW_KEYS,
    Count,
    added_lines,
    count_tier1a,
)
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis"
DIFF = (FIXTURES / "tier1a.diff").read_text()
NO_TESTS = (FIXTURES / "tier1a_no_tests.diff").read_text()
CLASSES = (
    "generated_or_artefact",
    "test_e2e",
    "test_unit",
    "test_unclassified",
    "docs",
    "configuration",
    "production",
)

NUMSTAT = (
    NumstatEntry("src/app.ts", 6, 2, False),
    NumstatEntry("tests/unit/app.test.ts", 5, 1, False),
    NumstatEntry("tests/e2e/flow.spec.ts", 3, 0, False),
    NumstatEntry("tests/helpers/util.py", 2, 0, False),
    NumstatEntry("tests/unit/test_x.py", 3, 0, False),
    NumstatEntry("tests/unit/old_test.py", 0, 4, False),
    NumstatEntry("docs/guide.md", 2, 1, False),
    NumstatEntry("package.json", 1, 1, False),
    NumstatEntry("pnpm-lock.yaml", 5, 3, False),
    NumstatEntry("src/new_name.ts", 1, 1, False),
    NumstatEntry("tests/unit/new.test.ts", 1, 1, False),
    NumstatEntry("assets/logo.png", 0, 0, True),
    NumstatEntry("src/café.ts", 1, 0, False),
)
NAME_STATUS = (
    NameStatus("M", "src/app.ts", None),
    NameStatus("M", "tests/unit/app.test.ts", None),
    NameStatus("A", "tests/e2e/flow.spec.ts", None),
    NameStatus("A", "tests/helpers/util.py", None),
    NameStatus("M", "tests/unit/test_x.py", None),
    NameStatus("D", "tests/unit/old_test.py", None),
    NameStatus("M", "docs/guide.md", None),
    NameStatus("M", "package.json", None),
    NameStatus("M", "pnpm-lock.yaml", None),
    NameStatus("R", "src/new_name.ts", "src/old_name.ts"),
    NameStatus("R", "tests/unit/new.test.ts", "tests/unit/old.test.ts"),
    NameStatus("A", "assets/logo.png", None),
    NameStatus("A", "src/café.ts", None),
)


def counts(
    numstat: tuple[NumstatEntry, ...],
    name_status: tuple[NameStatus, ...],
    diff: str,
    *,
    declaration: Declaration = DEFAULT_DECLARATION,
    hub: bool = False,
) -> dict[tuple[str, str | None], int]:
    found = count_tier1a(numstat, name_status, diff, declaration, hub=hub)
    table = {(c.metric_id, c.source): c.value for c in found}
    assert len(table) == len(found)
    return table


def single(path: str, lines: list[str], status: str = "M") -> dict[tuple[str, str | None], int]:
    body = "".join(f"+{line}\n" for line in lines)
    header = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    diff = f"{header}@@ -1 +1,{len(lines)} @@\n-x\n{body}"
    return counts(
        (NumstatEntry(path, len(lines), 1, False),),
        (NameStatus(status, path, None),),  # type: ignore[arg-type]
        diff,
    )


def test_every_signal_on_the_fixture_diff() -> None:
    table = counts(NUMSTAT, NAME_STATUS, DIFF)
    sizes = {"production": 8, "test_unit": 9, "test_e2e": 3, "test_unclassified": 2}
    sizes |= {"docs": 2, "configuration": 1, "generated_or_artefact": 5}
    removed = {"production": 3, "test_unit": 6, "test_e2e": 0, "test_unclassified": 0}
    removed |= {"docs": 1, "configuration": 1, "generated_or_artefact": 3}
    assert {k: v for (m, k), v in table.items() if m == "code.lines_added"} == sizes
    assert {k: v for (m, k), v in table.items() if m == "code.lines_removed"} == removed
    assert {k: v for (m, k), v in table.items() if m == "code.files_touched"} == {
        "added": 4,
        "modified": 8,
        "deleted": 1,
    }
    assert table[("code.suppressions_added", None)] == 4
    assert table[("code.type_escapes_added", "production")] == 3
    assert table[("code.type_escapes_added", "test")] == 2
    assert table[("code.skip_focus_markers_added", None)] == 4
    assert table[("code.preexisting_tests_changed", None)] == 3
    assert table[("code.preexisting_tests_deleted", None)] == 1
    assert table[("code.test_cases_static", None)] == 7
    assert table[("code.manifest_changes", None)] == 2
    assert {k: v for (m, k), v in table.items() if m == "code.test_files"} == {
        "test_unit:added": 0,
        "test_unit:modified": 3,
        "test_unit:deleted": 1,
        "test_e2e:added": 1,
        "test_e2e:modified": 0,
        "test_e2e:deleted": 0,
        "test_unclassified:added": 1,
        "test_unclassified:modified": 0,
        "test_unclassified:deleted": 0,
    }
    assert {k: v for (m, k), v in table.items() if m == "code.test_lines"} == {
        "test_unit:added": 9,
        "test_unit:removed": 6,
        "test_e2e:added": 3,
        "test_e2e:removed": 0,
        "test_unclassified:added": 2,
        "test_unclassified:removed": 0,
    }


def test_the_rows_are_the_same_whatever_the_diff_and_carry_their_rate_class() -> None:
    found = count_tier1a(NUMSTAT, NAME_STATUS, DIFF, DEFAULT_DECLARATION, hub=False)
    empty = count_tier1a((), (), "", DEFAULT_DECLARATION, hub=False)
    keys = [(c.metric_id, c.source) for c in found]
    assert keys == [(c.metric_id, c.source) for c in empty]
    assert keys == [k for k in ROW_KEYS if k[0] != "code.possible_secrets"]
    assert ("code.possible_secrets", None) in ROW_KEYS
    assert all(c.value == 0 for c in empty)
    by_key = {(c.metric_id, c.source): c for c in found}
    assert by_key[("code.lines_added", "production")].rate is None
    assert by_key[("code.files_touched", "added")].rate is None
    assert by_key[("code.type_escapes_added", "test")].rate == "test"
    assert by_key[("code.type_escapes_added", "production")].rate == "production"
    assert by_key[("code.suppressions_added", None)].rate == "production"
    assert all(c.combine == "sum" for c in found)


def test_the_type_escape_split_reads_each_class_apart() -> None:
    numstat = (
        NumstatEntry("src/a.ts", 120, 0, False),
        NumstatEntry("tests/unit/a.test.ts", 40, 0, False),
    )
    status = (NameStatus("A", "src/a.ts", None), NameStatus("A", "tests/unit/a.test.ts", None))
    prod = "".join("+x as any\n" if n < 3 else "+x\n" for n in range(120))
    test = "".join("+x as any\n" if n < 2 else "+x\n" for n in range(40))
    diff = (
        "diff --git a/src/a.ts b/src/a.ts\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/src/a.ts\n@@ -0,0 +1,120 @@\n"
        + prod
        + "diff --git a/tests/unit/a.test.ts b/tests/unit/a.test.ts\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/tests/unit/a.test.ts\n@@ -0,0 +1,40 @@\n" + test
    )
    table = counts(numstat, status, diff)
    assert table[("code.type_escapes_added", "production")] == 3
    assert table[("code.type_escapes_added", "test")] == 2
    assert table[("code.lines_added", "production")] == 120
    assert table[("code.lines_added", "test_unit")] == 40


def test_preexisting_tests_changed_and_deleted() -> None:
    status = (
        NameStatus("M", "tests/unit/test_x.py", None),
        NameStatus("D", "tests/unit/test_gone.py", None),
        NameStatus("T", "tests/unit/b.test.ts", None),
        NameStatus("A", "tests/unit/test_new.py", None),
        NameStatus("C", "tests/unit/test_copy.py", "tests/unit/test_x.py"),
        NameStatus("R", "tests/unit/test_moved.py", "tests/unit/test_was.py"),
        NameStatus("R", "tests/unit/test_from_prod.py", "src/was.py"),
        NameStatus("D", "src/gone.py", None),
        NameStatus("M", "src/kept.py", None),
    )
    table = counts((), status, "")
    assert table[("code.preexisting_tests_changed", None)] == 3
    assert table[("code.preexisting_tests_deleted", None)] == 1
    assert table[("code.test_files", "test_unit:added")] == 2
    assert table[("code.test_files", "test_unit:modified")] == 4
    assert table[("code.test_files", "test_unit:deleted")] == 1
    assert table[("code.files_touched", "added")] == 2
    assert table[("code.files_touched", "modified")] == 5
    assert table[("code.files_touched", "deleted")] == 2


def test_a_diff_with_no_test_files_reads_zero_for_every_test_signal() -> None:
    table = counts(
        (NumstatEntry("src/app.ts", 2, 1, False),), (NameStatus("M", "src/app.ts", None),), NO_TESTS
    )
    test_keys = [
        k
        for k in table
        if k[0] in {"code.test_files", "code.test_lines", "code.preexisting_tests_changed"}
        or k[0] in {"code.preexisting_tests_deleted", "code.test_cases_static"}
        or k == ("code.type_escapes_added", "test")
    ]
    assert len(test_keys) == 9 + 6 + 4
    assert all(table[k] == 0 for k in test_keys)
    assert table[("code.type_escapes_added", "production")] == 1
    assert table[("code.lines_added", "production")] == 2


@pytest.mark.parametrize(
    "line",
    [
        "// eslint-disable-next-line",
        "// @ts-ignore",
        "/* @ts-nocheck */",
        "x = 1  # noqa: E501",
        "x = 1  # type: ignore",
        "//nolint:gosec",
        '@SuppressWarnings("unchecked")',
        "# pylint: disable=unused-import",
        "#[allow(dead_code)]",
    ],
)
def test_each_suppression_pattern_counts(line: str) -> None:
    assert single("src/x.ts", [line, "plain"])[("code.suppressions_added", None)] == 1


@pytest.mark.parametrize(
    "line",
    [
        "let a: any = 1;",
        "v as any;",
        "const x = <any>y;",
        "a as unknown as B",
        "// @ts-expect-error",
        "x: typing.Any = 1",
        "y = cast(Any, z)",
        "var v interface{}",
    ],
)
def test_each_type_escape_pattern_counts(line: str) -> None:
    table = single("src/x.ts", [line, "let b: anything = 1;", "x as anyone"])
    assert table[("code.type_escapes_added", "production")] == 1


@pytest.mark.parametrize(
    "line",
    [
        "a.skip(",
        "a.only(",
        "xit('x')",
        "xdescribe('x')",
        "fit('x')",
        "fdescribe('x')",
        "@pytest.mark.skip",
        "@pytest.mark.xfail",
        "t.Skip(",
        "@Disabled",
        "@Ignore",
    ],
)
def test_each_skip_and_focus_marker_counts(line: str) -> None:
    assert single("src/x.ts", [line, "plain"])[("code.skip_focus_markers_added", None)] == 1


@pytest.mark.parametrize(
    "line",
    [
        "it('x', () => {",
        "  test('x', () => {",
        "def test_a():",
        "async def test_a():",
        "func TestA(t *T) {",
        "@Test",
    ],
)
def test_each_test_case_opener_counts(line: str) -> None:
    table = single("src/x.ts", [line, "x.test()", "xit('x')"])
    assert table[("code.test_cases_static", None)] == 1


@pytest.mark.parametrize(
    "path",
    [
        "package.json",
        "web/pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "uv.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "go.sum",
        "Cargo.lock",
    ],
)
def test_each_manifest_and_lock_file_counts(path: str) -> None:
    status = (NameStatus("M", path, None),)
    assert counts((), status, "")[("code.manifest_changes", None)] == 1


def test_an_ordinary_file_is_not_a_manifest() -> None:
    status = (NameStatus("M", "src/requirements.py", None), NameStatus("D", "docs/go.md", None))
    assert counts((), status, "")[("code.manifest_changes", None)] == 0


def test_pattern_signals_count_every_class_but_type_escapes_only_code_classes() -> None:
    line = "x as any // eslint-disable-line"
    for path, escapes in (("docs/a.md", 0), ("config.yaml", 0), ("dist/a.js", 0), ("src/a.ts", 1)):
        table = single(path, [line])
        assert table[("code.suppressions_added", None)] == 1
        assert table[("code.type_escapes_added", "production")] == escapes
    for path in ("tests/unit/a.ts", "tests/e2e/a.ts", "tests/other/a.ts"):
        assert single(path, [line])[("code.type_escapes_added", "test")] == 1


def test_the_hub_flag_and_declaration_choose_the_class() -> None:
    numstat = (
        NumstatEntry("initiatives/a.md", 2, 0, False),
        NumstatEntry("checks/a.ts", 3, 0, False),
    )
    assert counts(numstat, (), "", hub=True)[("code.lines_added", "generated_or_artefact")] == 2
    assert counts(numstat, (), "", hub=False)[("code.lines_added", "docs")] == 2
    declared = Declaration(tests_unit=("checks/*.ts",))
    assert counts(numstat, (), "", declaration=declared)[("code.lines_added", "test_unit")] == 3


def test_added_lines_by_head_path() -> None:
    found = added_lines(DIFF)
    assert found["src/app.ts"][0] == "// eslint-disable-next-line no-console"
    assert found["src/app.ts"][3] == "++counter;"
    assert len(found["src/app.ts"]) == 6
    assert found["src/café.ts"] == ("export const x = 1;",)
    assert found["src/new_name.ts"] == ("export const n = 2;",)
    assert found["tests/unit/new.test.ts"] == ('  it("renamed", () => {',)
    assert "tests/unit/old_test.py" not in found
    assert "assets/logo.png" not in found
    assert sum(len(v) for v in found.values()) == 8 + 9 + 3 + 2 + 2 + 1 + 5


def test_header_look_alikes_inside_a_hunk_are_content() -> None:
    diff = (
        "diff --git a/a.sql b/a.sql\n--- a/a.sql\n+++ b/a.sql\n@@ -1 +1,2 @@\n"
        "--- old comment\n+++ new comment\n++++ b/fake.ts\n"
        "diff --git a/b.sql b/b.sql\n--- a/b.sql\n+++ b/b.sql\n@@ -3,0 +4 @@\n+last\n"
        "\\ No newline at end of file\n"
    )
    assert added_lines(diff) == {
        "a.sql": ("++ new comment", "+++ b/fake.ts"),
        "b.sql": ("last",),
    }


def test_context_lines_and_no_newline_markers_inside_a_hunk_are_not_added_lines() -> None:
    diff = (
        "diff --git a/a.ts b/a.ts\n--- a/a.ts\n+++ b/a.ts\n@@ -1,3 +1,3 @@\n"
        " keep\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n tail\n"
    )
    assert added_lines(diff) == {"a.ts": ("new",)}


def test_escapes_in_a_quoted_path() -> None:
    diff = (
        'diff --git "a/a\\"b\\t\\\\c.ts" "b/a\\"b\\t\\\\c.ts"\n--- "a/a\\"b\\t\\\\c.ts"\n'
        '+++ "b/a\\"b\\t\\\\c.ts"\n@@ -0,0 +1 @@\n+x\n'
    )
    assert added_lines(diff) == {'a"b\t\\c.ts': ("x",)}


def test_an_empty_diff_has_no_added_lines() -> None:
    assert added_lines("") == {}


def test_count_is_a_frozen_value() -> None:
    count = Count("code.x", None, 1, None)
    assert count.combine == "sum"
    with pytest.raises(AttributeError):
        count.value = 2  # type: ignore[misc]
