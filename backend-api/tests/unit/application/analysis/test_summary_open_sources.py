"""Open-ended sources at Run scope: `code.deps_licences` (Operator ruling 2026-11-13).

A repository whose lookups ran counts 0 for a licence it does not hold; only a repository
whose lookups did not run makes a licence row partial; the 0 row without a licence goes when
any licence row exists. Every other metric's summary is what it was.
"""

from __future__ import annotations

import pytest

from orchestrator.application.analysis import summary
from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.summary import OPEN_SOURCE_METRICS, summarise
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.values import MetricValue

LICENCES = "code.deps_licences"
LINES = Count("code.lines_added", "production", 300, None)


def repo(path: str, *counts: Count, words: dict[str, str] | None = None) -> RepositorySignals:
    return RepositorySignals(path, "ok", "", (LINES, *counts), words or {})


def licence(source: str | None, value: int) -> Count:
    return Count(LICENCES, source, value, "production")


def run_rows(values: list[MetricValue], metric_id: str = LICENCES) -> dict[str | None, MetricValue]:
    return {
        v.source: v
        for v in values
        if v.metric_id == metric_id
        and v.scope_type == "run"
        and v.source != "per_100"
        and not (v.source or "").endswith(":per_100")
    }


def test_only_the_licences_metric_is_open_ended() -> None:
    assert OPEN_SOURCE_METRICS == ("code.deps_licences",)


def test_a_licence_another_repository_lacks_counts_zero_there_not_missing() -> None:
    values = summarise([repo("web", licence("MIT", 2)), repo("api", licence("Apache-2.0", 1))])
    rows = run_rows(values)
    assert set(rows) == {"MIT", "Apache-2.0"}
    assert rows["MIT"].value_num == 2
    assert rows["Apache-2.0"].value_num == 1
    assert rows["MIT"].missing is None
    assert rows["Apache-2.0"].missing is None


def test_a_repository_whose_lookups_did_not_run_is_the_only_partial() -> None:
    off = repo("api", words={LICENCES: "not run — lookups off"})
    rows = run_rows(summarise([repo("web", licence("MIT", 1)), off]))
    assert set(rows) == {"MIT"}
    assert rows["MIT"].missing == "partial"
    assert (rows["MIT"].partial_n, rows["MIT"].partial_m) == (1, 2)


def test_the_zero_row_without_a_licence_goes_when_a_licence_row_exists() -> None:
    values = summarise([repo("web", licence(None, 0)), repo("api", licence("MIT", 1))])
    rows = run_rows(values)
    assert set(rows) == {"MIT"}
    assert rows["MIT"].missing is None
    web = [v for v in values if v.metric_id == LICENCES and v.scope_key == "web"]
    assert [(v.source, v.value_num) for v in web if v.source is None] == [(None, 0)]


def test_the_zero_row_stays_when_no_repository_holds_a_licence() -> None:
    rows = run_rows(summarise([repo("web", licence(None, 0)), repo("api", licence(None, 0))]))
    assert set(rows) == {None}
    assert rows[None].value_num == 0


def test_every_repository_without_lookups_keeps_the_word() -> None:
    off = {LICENCES: "not run — lookups off"}
    rows = run_rows(summarise([repo("web", words=off), repo("api", words=off)]))
    assert rows[None].missing == "not run — lookups off"


def test_a_failed_repository_is_missing_for_the_licences_too() -> None:
    failed = RepositorySignals("api", "failed", "clone failed", (), {})
    rows = run_rows(summarise([repo("web", licence("MIT", 1)), failed]))
    assert (rows["MIT"].partial_n, rows["MIT"].partial_m) == (1, 2)


def key(value: MetricValue) -> tuple[object, ...]:
    return (value.metric_id, value.scope_type, value.scope_key, value.source)


def test_every_other_metric_summarises_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    signals = [
        repo(
            "web",
            licence("MIT", 1),
            Count("code.deps_changed", "added", 2, "production"),
            Count("code.duplication_added", None, 4, "production"),
            Count("code.functions_over_cyclomatic", "count", 1, None, "sum"),
            Count("code.functions_over_cyclomatic", "worst", 22, None, "max"),
            Count("code.secrets_found", "gitleaks", 1, None),
            words={"code.deps_recent": "not run — lookups off"},
        ),
        repo(
            "api",
            licence("Apache-2.0", 1),
            Count("code.deps_changed", "removed", 1, "production"),
            Count("code.functions_over_cyclomatic", "count", 2, None, "sum"),
            Count("code.functions_over_cyclomatic", "worst", 30, None, "max"),
        ),
        RepositorySignals("docs", "failed", "boom", (), {}),
    ]
    now = [v for v in summarise(signals) if v.metric_id != LICENCES]
    monkeypatch.setattr(summary, "OPEN_SOURCE_METRICS", ())
    before = [v for v in summarise(signals) if v.metric_id != LICENCES]
    assert now == before
    assert {key(v) for v in now} == {key(v) for v in before}
