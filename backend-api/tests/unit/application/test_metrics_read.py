"""Reading a Run's metrics (epic 2 story 5: AC4 read half, AC9, `methods_changed`)."""

from __future__ import annotations

from uuid import UUID

import pytest

from orchestrator.application.metrics.values import MetricValue
from orchestrator.application.use_cases.metrics_read import (
    MetricsQueryPorts,
    calculation_for,
    list_versions,
    run_metrics,
)
from orchestrator.domain.entities.metric_results import MetricCalculation, ResultVersion
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_fixed_run import RUN_ID, T0, build_fixed_run
from tests.unit.application.test_metric_versions import stored
from tests.unit.fakes.metric_results import (
    FakeMetricCalculationRepository,
    FakeResultVersionRepository,
)

TWO = 2


def a_query(status: str = "done") -> MetricsQueryPorts:
    fixed = build_fixed_run()
    fixed.ports.runs.runs[RUN_ID] = fixed.run.model_copy(update={"status": status})  # type: ignore[attr-defined]
    return MetricsQueryPorts(
        read=fixed.ports,
        versions=FakeResultVersionRepository(),
        calculations=FakeMetricCalculationRepository(),
    )


def add_version(ports: MetricsQueryPorts, n: int, methods: tuple[str, ...] = ()) -> ResultVersion:
    version = ResultVersion(
        id=new_id(),
        run_id=RUN_ID,
        n=n,
        calculated_at=T0,
        entry_point=("manual",),
        methods=methods,
    )
    ports.versions.add(version, [stored(scope_key=f"v{n}")])
    return version


def test_a_live_run_answers_values_so_far_and_stores_nothing() -> None:
    ports = a_query("running")

    result = run_metrics(ports, RUN_ID, None)

    assert (result.version, result.values_so_far, result.latest_n) == (None, True, None)
    assert result.items
    assert all(isinstance(item, MetricValue) for item in result.items)
    assert ports.versions.versions == []  # type: ignore[attr-defined]


def test_an_ended_run_without_a_version_answers_nothing() -> None:
    result = run_metrics(a_query(), RUN_ID, None)

    assert (result.version, result.values_so_far, result.items) == (None, False, [])


def test_the_latest_version_answers_when_none_is_asked_for() -> None:
    ports = a_query()
    add_version(ports, 1)
    two = add_version(ports, 2)

    result = run_metrics(ports, RUN_ID, None)

    assert result.version == two
    assert result.latest_n == TWO
    assert [v.scope_key for v in result.items] == ["v2"]  # type: ignore[union-attr]


def test_an_older_version_is_returned_unchanged_after_a_newer_one() -> None:
    ports = a_query()
    add_version(ports, 1)
    first = run_metrics(ports, RUN_ID, 1)
    add_version(ports, 2)

    again = run_metrics(ports, RUN_ID, 1)

    assert (again.version, again.items) == (first.version, first.items)
    assert (first.latest_n, again.latest_n) == (1, 2)
    assert run_metrics(ports, RUN_ID, 2).version is not None


def test_a_version_the_run_lacks_is_not_found() -> None:
    ports = a_query()
    add_version(ports, 1)

    with pytest.raises(NotFound):
        run_metrics(ports, RUN_ID, 5)


def test_an_unknown_run_is_not_found_everywhere() -> None:
    ports = a_query()
    unknown: UUID = new_id()

    with pytest.raises(NotFound):
        run_metrics(ports, unknown, None)
    with pytest.raises(NotFound):
        list_versions(ports, unknown)
    with pytest.raises(NotFound):
        calculation_for(ports, unknown, 1)


def test_the_versions_list_the_methods_each_one_changed() -> None:
    ports = a_query()
    add_version(ports, 1, ("a.x@1", "b.y@1"))
    add_version(ports, 2, ("a.x@1", "b.y@2"))

    views = list_versions(ports, RUN_ID)

    assert [(v.n, v.methods_changed, v.entry_point) for v in views] == [
        (1, [], ("manual",)),
        (2, ["b.y@1", "b.y@2"], ("manual",)),
    ]


def test_a_calculation_is_read_by_its_target_version_newest_first() -> None:
    ports = a_query()
    for state, offset in (("failed", 0), ("done", 1)):
        ports.calculations.add(
            MetricCalculation(
                id=new_id(),
                run_id=RUN_ID,
                target_n=1,
                state=state,  # type: ignore[arg-type]
                entry_point=("manual",),
                queued_at=T0.replace(minute=offset),
            )
        )

    assert calculation_for(ports, RUN_ID, 1).state == "done"
    with pytest.raises(NotFound):
        calculation_for(ports, RUN_ID, 2)
