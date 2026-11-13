"""The per-repository and Run summary of the Tier 1a counts (story 5.2, AC1, AC3, AC6, AC7)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.summary import (
    NOT_RUN,
    PER_LINES,
    RATE_MIN_LINES,
    RAW_ONLY,
    SMALL_CHANGE,
    SMALL_CHANGE_LINES,
    not_run,
    summarise,
)
from orchestrator.application.analysis.tier1a import ROW_KEYS, Count
from orchestrator.application.metrics.values import PARTIAL, MetricValue


def repo(
    path: str,
    *counts: Count,
    production: int | None = None,
    test: dict[str, int] | None = None,
    words: dict[str, str] | None = None,
) -> RepositorySignals:
    lines = (
        [Count("code.lines_added", "production", production, None)]
        if production is not None
        else []
    )
    lines += [Count("code.lines_added", k, v, None) for k, v in (test or {}).items()]
    return RepositorySignals(path, "ok", "", (*lines, *counts), words or {}, (), {})


def failed(path: str, output: str) -> RepositorySignals:
    return RepositorySignals(path, "failed", output, (), {}, (), {})


def pick(
    values: list[MetricValue], metric: str, scope: str, source: str | None = None
) -> list[MetricValue]:
    return [
        v for v in values if v.metric_id == metric and v.scope_key == scope and v.source == source
    ]


def one(
    values: list[MetricValue], metric: str, scope: str, source: str | None = None
) -> MetricValue:
    (found,) = pick(values, metric, scope, source)
    return found


def test_the_constants_are_the_published_thresholds() -> None:
    assert (RATE_MIN_LINES, SMALL_CHANGE_LINES, PER_LINES) == (50, 200, 100)
    assert RAW_ONLY == "raw only"
    assert SMALL_CHANGE == "small change"
    assert not_run("boom") == "not run — boom"
    assert NOT_RUN == "not run"


def test_type_escapes_read_production_and_test_each_against_its_own_class() -> None:
    values = summarise(
        [
            repo(
                ".",
                Count("code.type_escapes_added", "production", 3, "production"),
                Count("code.type_escapes_added", "test", 2, "test"),
                production=120,
                test={"test_unit": 40},
            )
        ]
    )
    raw = one(values, "code.type_escapes_added", ".", "production")
    assert raw.value_num == 3
    assert raw.unit == "count"
    assert (raw.scope_type, raw.repository, raw.method_id) == (
        "repository",
        ".",
        "code.type_escapes_added@1",
    )
    rate = one(values, "code.type_escapes_added", ".", "production:per_100")
    assert rate.value_num == Decimal("2.50")
    assert rate.unit == "per 100 production lines"
    assert rate.missing is None
    test_raw = one(values, "code.type_escapes_added", ".", "test")
    assert test_raw.value_num == 2
    test_rate = one(values, "code.type_escapes_added", ".", "test:per_100")
    assert test_rate.value_num is None
    assert test_rate.missing == "raw only"
    assert test_rate.unit == "per 100 test lines"


def test_a_count_without_a_source_has_a_per_100_row_and_sizes_have_none() -> None:
    values = summarise(
        [repo(".", Count("code.suppressions_added", None, 3, "production"), production=60)]
    )
    assert one(values, "code.suppressions_added", ".").value_num == 3
    assert one(values, "code.suppressions_added", ".", "per_100").value_num == Decimal("5.00")
    assert pick(values, "code.lines_added", ".", "production:per_100") == []
    assert pick(values, "code.lines_added", ".", "per_100") == []


def test_the_test_denominator_is_all_three_test_classes() -> None:
    values = summarise(
        [
            repo(
                ".",
                Count("code.type_escapes_added", "test", 1, "test"),
                production=500,
                test={"test_unit": 20, "test_e2e": 20, "test_unclassified": 10},
            )
        ]
    )
    assert one(values, "code.type_escapes_added", ".", "test:per_100").value_num == Decimal("2.00")


def test_the_rate_boundary_is_fifty_lines() -> None:
    def rate(lines: int) -> MetricValue:
        count = Count("code.suppressions_added", None, 1, "production")
        return one(
            summarise([repo(".", count, production=lines)]),
            "code.suppressions_added",
            ".",
            "per_100",
        )

    assert rate(49).missing == "raw only"
    assert rate(49).value_num is None
    assert rate(50).value_num == Decimal("2.00")
    assert rate(50).missing is None


def test_rates_round_half_up() -> None:
    count = Count("code.suppressions_added", None, 1, "production")
    assert one(
        summarise([repo(".", count, production=160)]), "code.suppressions_added", ".", "per_100"
    ).value_num == Decimal("0.63")
    count = Count("code.suppressions_added", None, 1, "production")
    assert one(
        summarise([repo(".", count, production=64)]), "code.suppressions_added", ".", "per_100"
    ).value_num == Decimal("1.56")


def test_two_repositories_and_the_run_row() -> None:
    values = summarise(
        [
            repo("a", Count("code.suppressions_added", None, 2, "production"), production=30),
            repo("b", Count("code.suppressions_added", None, 1, "production"), production=40),
        ]
    )
    for path, count in (("a", 2), ("b", 1)):
        assert one(values, "code.suppressions_added", path).value_num == count
        assert one(values, "code.suppressions_added", path, "per_100").missing == "raw only"
    run = one(values, "code.suppressions_added", "run")
    assert (run.scope_type, run.repository, run.value_num, run.missing) == ("run", None, 3, None)
    assert one(values, "code.suppressions_added", "run", "per_100").value_num == Decimal("4.29")
    assert one(values, "code.lines_added", "run", "production").value_num == 70


def test_the_run_rate_is_recomputed_from_totals_not_averaged() -> None:
    values = summarise(
        [
            repo("a", Count("code.suppressions_added", None, 1, "production"), production=50),
            repo("b", Count("code.suppressions_added", None, 9, "production"), production=450),
        ]
    )
    assert one(values, "code.suppressions_added", "a", "per_100").value_num == Decimal("2.00")
    assert one(values, "code.suppressions_added", "run", "per_100").value_num == Decimal("2.00")


def test_a_failed_repository_reads_not_run_and_the_run_total_is_partial() -> None:
    values = summarise(
        [
            failed("a", "commit missing: h1\nmore lines"),
            repo("b", Count("code.suppressions_added", None, 4, "production"), production=100),
        ]
    )
    word = one(values, "code.suppressions_added", "a")
    assert word.value_num is None
    assert word.missing == "not run — commit missing: h1"
    assert {
        (m, s) for m, s in ((v.metric_id, v.source) for v in values if v.scope_key == "a")
    } == set(ROW_KEYS)
    run = one(values, "code.suppressions_added", "run")
    assert (run.value_num, run.missing, run.partial_n, run.partial_m) == (4, PARTIAL, 1, 2)
    rate = one(values, "code.suppressions_added", "run", "per_100")
    assert (rate.value_num, rate.missing) == (Decimal("4.00"), PARTIAL)
    sizes = one(values, "code.lines_added", "run", "production")
    assert (sizes.value_num, sizes.missing, sizes.partial_n, sizes.partial_m) == (
        100,
        PARTIAL,
        1,
        2,
    )


def test_when_no_repository_ran_the_run_row_reads_their_common_word() -> None:
    same = summarise([failed("a", "boom"), failed("b", "boom")])
    assert one(same, "code.suppressions_added", "run").missing == "not run — boom"
    assert one(same, "code.suppressions_added", "run").value_num is None
    empty = summarise([failed("a", ""), failed("b", "")])
    assert one(empty, "code.suppressions_added", "run").missing == "not run"
    assert one(empty, "code.suppressions_added", "a").missing == "not run"
    different = summarise([failed("a", "boom"), failed("b", "bang")])
    assert one(different, "code.suppressions_added", "run").missing == "not run"
    assert {v.scope_key for v in different} == {"a", "b", "run"}
    assert not any(v.source and v.source.endswith("per_100") for v in different)


def test_a_signal_that_could_not_be_measured_is_a_word_and_makes_the_run_partial() -> None:
    secret = Count("code.possible_secrets", None, 2, "production")
    values = summarise(
        [
            repo("a", secret, production=100),
            repo(
                "b",
                production=100,
                words={"code.possible_secrets": "not run — gitleaks: timed out"},
            ),
        ]
    )
    word = one(values, "code.possible_secrets", "b")
    assert (word.value_num, word.missing) == (None, "not run — gitleaks: timed out")
    assert pick(values, "code.possible_secrets", "b", "per_100") == []
    run = one(values, "code.possible_secrets", "run")
    assert (run.value_num, run.missing, run.partial_n, run.partial_m) == (2, PARTIAL, 1, 2)
    assert one(values, "code.possible_secrets", "run", "per_100").value_num == Decimal("2.00")


def test_a_signal_no_repository_could_measure_reads_the_common_word_on_the_run_row() -> None:
    words = {"code.possible_secrets": "not run — gitleaks: timed out"}
    values = summarise(
        [repo("a", production=10, words=words), repo("b", production=10, words=words)]
    )
    run = one(values, "code.possible_secrets", "run")
    assert (run.value_num, run.missing) == (None, "not run — gitleaks: timed out")
    mixed = summarise(
        [
            repo("a", production=10, words=words),
            repo("b", production=10, words={"code.possible_secrets": "other"}),
        ]
    )
    assert one(mixed, "code.possible_secrets", "run").missing == "not run"


def test_duplication_below_two_hundred_production_lines_is_a_small_change() -> None:
    dup = Count("code.duplication_added", None, 12, "production")
    values = summarise([repo("a", dup, production=150)])
    small = one(values, "code.duplication_added", "a", "small_change")
    assert (small.value_num, small.missing) == (None, "small change")
    assert one(values, "code.duplication_added", "run", "small_change").missing == "small change"
    assert one(values, "code.duplication_added", "a").value_num == 12
    for lines in (200, 5000):
        assert (
            pick(
                summarise([repo("a", dup, production=lines)]),
                "code.duplication_added",
                "a",
                "small_change",
            )
            == []
        )


def test_the_small_change_row_is_decided_per_scope() -> None:
    dup = Count("code.duplication_added", None, 1, "production")
    values = summarise([repo("a", dup, production=150), repo("b", dup, production=150)])
    assert one(values, "code.duplication_added", "a", "small_change")
    assert one(values, "code.duplication_added", "b", "small_change")
    assert pick(values, "code.duplication_added", "run", "small_change") == []


def test_a_maximum_is_the_larger_value_not_the_sum() -> None:
    worst = "code.functions_over_cyclomatic"
    values = summarise(
        [
            repo("a", Count(worst, None, 3, None, "max"), production=10),
            repo("b", Count(worst, None, 7, None, "max"), production=10),
        ]
    )
    assert one(values, worst, "run").value_num == 7
    assert pick(values, worst, "run", "per_100") == []


def test_every_test_row_is_a_figure_zero_when_the_diff_has_no_tests() -> None:
    zeros = [
        Count("code.test_files", "test_unit:added", 0, "production"),
        Count("code.test_cases_static", None, 0, "production"),
    ]
    values = summarise([repo(".", *zeros, production=10)])
    row = one(values, "code.test_files", ".", "test_unit:added")
    assert (row.value_num, row.missing) == (0, None)
    assert one(values, "code.test_cases_static", ".").value_num == 0
    assert one(values, "code.test_cases_static", ".").missing is None


def test_units_follow_the_metric() -> None:
    counts = (
        Count("code.lines_added", "production", 1, None),
        Count("code.test_lines", "test_unit:added", 1, "production"),
        Count("code.files_touched", "added", 1, None),
        Count("code.test_files", "test_unit:added", 1, "production"),
        Count("code.manifest_changes", None, 1, "production"),
    )
    values = summarise([RepositorySignals(".", "ok", "", counts, {}, (), {})])
    assert one(values, "code.lines_added", ".", "production").unit == "lines"
    assert one(values, "code.test_lines", ".", "test_unit:added").unit == "lines"
    assert one(values, "code.files_touched", ".", "added").unit == "files"
    assert one(values, "code.test_files", ".", "test_unit:added").unit == "files"
    assert one(values, "code.manifest_changes", ".").unit == "count"


def test_no_signals_no_values() -> None:
    assert summarise([]) == []
