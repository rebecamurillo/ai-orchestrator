"""Tier 2 test-case signals on parsed cases (epic 6 story 1, AC3, AC4)."""

from __future__ import annotations

import json

from orchestrator.application.analysis.tier2_cases import (
    ABSENT,
    absent,
    executed_counts,
    fail_to_pass,
    identity,
    mapped,
    verdict,
)
from orchestrator.application.analysis.tier2_reports import Case

SOURCE = "tests/unit/test_x.py"
ADDED, REMOVED, TOTAL = 4, 1, 13


def case(name: str, outcome: str = "passed", message: str = "", file: str | None = SOURCE) -> Case:
    return Case(file, "t", name, outcome, message)  # type: ignore[arg-type]


def test_mapped_follows_a_rename_and_keeps_none() -> None:
    assert mapped("a", {"a": "b"}) == "b"
    assert mapped("c", {"a": "b"}) == "c"
    assert mapped(None, {"a": "b"}) is None
    assert identity(case("n", file="a"), {"a": "b"}) == ("b", "t", "n")


def test_cases_added_removed_and_total_per_class() -> None:
    base = [case(f"n{i}") for i in range(10)]
    head = [case(f"n{i}") for i in range(1, 10)] + [case(f"new{i}") for i in range(ADDED)]
    counts = executed_counts(
        base, head, {}, lambda file: "unclassified" if file is None else "test_unit"
    )
    assert {c.source: c.value for c in counts} == {
        "test_unit:added": ADDED,
        "test_unit:removed": REMOVED,
        "test_unit:total": TOTAL,
    }


def test_a_renamed_file_does_not_count_its_cases_as_added_and_removed() -> None:
    base = [case("n", file="old.py")]
    head = [case("n", file="new.py")]
    counts = executed_counts(base, head, {"old.py": "new.py"}, lambda file: "test_unit")
    assert {c.source: c.value for c in counts} == {
        "test_unit:added": 0,
        "test_unit:removed": 0,
        "test_unit:total": 1,
    }


def test_each_outcome_of_a_new_case() -> None:
    produced = [
        case("p"),
        case("s", "skipped", "why"),
        case("i", "error", "ModuleNotFoundError: m"),
        case("f", "failed", "AssertionError"),
    ]
    assert verdict(case("p"), produced) == ("pass", "")
    assert verdict(case("s"), produced) == ("skipped", "why")
    assert verdict(case("i"), produced) == ("import_error", "import error")
    assert verdict(case("f"), produced) == ("fail", "AssertionError")
    assert verdict(case("gone", file="other.py"), produced) == ("not_run", ABSENT)


def test_an_absent_case_is_an_import_error_when_a_collection_error_names_its_file() -> None:
    collection = Case(None, "tests.unit.test_x", "collect", "error", "ImportError")
    assert absent(case("a"), [collection]) == ("import_error", "import error")
    assert absent(case("a", file=None), [collection]) == ("not_run", ABSENT)
    assert absent(case("a"), []) == ("not_run", ABSENT)


def test_fail_to_pass_counts_every_outcome_and_lists_each_case() -> None:
    new = [case("f"), case("g")]
    counts, body = fail_to_pass(new, [case("f", "failed", "boom")])
    assert {c.source: c.value for c in counts} == {
        "fail": 1,
        "pass": 0,
        "import_error": 0,
        "skipped": 0,
        "not_run": 1,
    }
    assert [row["outcome"] for row in json.loads(body)] == ["fail", "not_run"]
