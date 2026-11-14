"""`step_values` and `not_catalogued`: the Run's own repository's step figures (epic 6 story 3)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.step_values import not_catalogued, step_values

JUNIT = "step.bench-v1.heldout_tests"
COVER = "step.bench-v1.coverage"


def signals(path: str = ".", counts=(), words=None, undeclared=()) -> RepositorySignals:  # type: ignore[no-untyped-def]
    return RepositorySignals(path, "ok", "", tuple(counts), words or {}, not_catalogued=undeclared)


def by_source(values):  # type: ignore[no-untyped-def]
    return {(v.metric_id, v.source): v for v in values}


def test_each_count_is_a_run_row_with_its_source_and_method() -> None:
    counts = [Count(JUNIT, "passed", 18, None), Count(JUNIT, "failed", 2, None)]

    values = by_source(step_values([signals(counts=counts)]))

    passed = values[(JUNIT, "passed")]
    assert (passed.value_num, passed.unit, passed.method_id) == (18, "count", f"{JUNIT}@1")
    assert (passed.scope_type, passed.scope_key, passed.repository) == ("run", "run", ".")
    assert values[(JUNIT, "failed")].value_num == 2  # noqa: PLR2004


def test_covered_and_instrumented_lines_add_a_share_in_percent() -> None:
    counts = [Count(COVER, "covered", 30, None), Count(COVER, "instrumented", 40, None)]

    values = by_source(step_values([signals(counts=counts)]))

    assert values[(COVER, "covered")].unit == "lines"
    assert values[(COVER, "instrumented")].unit == "lines"
    share = values[(COVER, "share")]
    assert (share.value_num, share.unit) == (Decimal("75.00"), "%")


def test_a_share_rounds_half_up_to_hundredths() -> None:
    counts = [Count(COVER, "covered", 1, None), Count(COVER, "instrumented", 8, None)]

    assert by_source(step_values([signals(counts=counts)]))[(COVER, "share")].value_num == Decimal(
        "12.50"
    )
    counts = [Count(COVER, "covered", 1, None), Count(COVER, "instrumented", 3, None)]
    assert by_source(step_values([signals(counts=counts)]))[(COVER, "share")].value_num == Decimal(
        "33.33"
    )


def test_no_instrumented_line_is_a_word_for_the_share() -> None:
    counts = [Count(COVER, "covered", 0, None), Count(COVER, "instrumented", 0, None)]

    share = by_source(step_values([signals(counts=counts)]))[(COVER, "share")]

    assert (share.value_num, share.missing) == (None, "n/a — no line instrumented")


def test_a_step_word_is_a_row_without_a_figure() -> None:
    [value] = step_values([signals(words={JUNIT: "n/a — no file matches out/x.xml"})])

    assert (value.metric_id, value.value_num, value.missing, value.source) == (
        JUNIT,
        None,
        "n/a — no file matches out/x.xml",
        None,
    )


def test_other_tiers_counts_and_words_are_not_step_values() -> None:
    counts = [Count("code.lines_added", "production", 5, None), Count("x.y", None, 1, None)]
    other = {"code.possible_secrets": "not run"}

    assert step_values([signals(counts=counts, words=other)]) == []


def test_a_sourceless_step_count_is_skipped() -> None:
    assert step_values([signals(counts=[Count(JUNIT, None, 1, None)])]) == []


def test_member_repositories_are_ignored() -> None:
    member = signals("repos/x", [Count(JUNIT, "passed", 9, None)], undeclared=("a.xml",))

    assert step_values([member]) == []
    assert not_catalogued([member]) == ()


def test_the_root_repositorys_undeclared_files_are_returned() -> None:
    code = [signals("repos/x", undeclared=("m.xml",)), signals(undeclared=("out/other.xml",))]

    assert not_catalogued(code) == ("out/other.xml",)
