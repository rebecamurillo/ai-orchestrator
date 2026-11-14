"""Spend this month and a project's Runs (epic 4 story 1: AC9, AC10, AC11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.use_cases.metrics_spend import (
    MetricsHomePorts,
    project_runs,
    spend_this_month,
)
from orchestrator.domain.entities.facts import FactSet
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.metric_results import FakeResultVersionRepository
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.run_records import FakeRunRepositoryRecords
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
THIS_MONTH = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
LAST_MONTH = datetime(2026, 10, 31, 23, 59, tzinfo=UTC)


def a_project(name: str) -> Project:
    return Project(
        id=new_id(),
        slug=name,
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(project: Project, **over: Any) -> Run:
    fields: dict[str, Any] = {
        "id": new_id(),
        "project_id": project.id,
        "repository_id": new_id(),
        "template_name": "initiative-hub",
        "template_version": 3,
        "status": "done",
        "budget_usd": None,
        "created_at": THIS_MONTH,
        "started_at": THIS_MONTH,
        "ended_at": THIS_MONTH + timedelta(seconds=90),
        "label": "a run",
        "inputs": {"harness": "claude", "base_branch": "main"},
    }
    fields.update(over)
    return Run(**fields)


def a_set(run: Run, flag: bool | None, extractor: str = "claude") -> FactSet:
    return FactSet(
        id=new_id(),
        attempt_id=new_id(),
        run_id=run.id,
        extractor=extractor,
        extractor_version=1,
        read_at=NOW,
        status="ok",
        subscription=flag,
    )


class World:
    def __init__(self, projects: list[Project], runs: list[Run]) -> None:
        self.runs = FakeRunRepository(runs)
        self.fact_sets = FakeFactSetRepository()
        self.versions = FakeResultVersionRepository()
        self.records = FakeRunRepositoryRecords()
        self.ports = MetricsHomePorts(
            projects=FakeProjectRepository(projects),
            runs=self.runs,
            versions=self.versions,
            fact_sets=self.fact_sets,
            run_records=self.records,
            clock=FakeClock(NOW),
        )


def test_spend_sums_this_months_runs_and_sets_cancelled_apart() -> None:
    familio, quiet = a_project("familio"), a_project("quiet")
    runs = [
        a_run(familio, gateway_spend_usd=Decimal("2.00"), harness_spend_usd=Decimal("2.50")),
        a_run(
            familio,
            status="cancelled",
            gateway_spend_usd=Decimal("1.00"),
            harness_spend_usd=Decimal("1.20"),
            gateway_reported=True,
        ),
        a_run(familio, started_at=LAST_MONTH, gateway_spend_usd=Decimal("40")),
        a_run(familio, started_at=None, status="queued"),
    ]
    world = World([familio, quiet], runs)

    spend = {item.project_name: item for item in spend_this_month(world.ports)}

    assert [spend["familio"].gateway, spend["familio"].harness] == ["3.00", "3.70"]
    assert spend["familio"].runs == 2  # noqa: PLR2004
    assert (spend["familio"].cancelled.gateway, spend["familio"].cancelled.harness) == (
        "1.00",
        "1.20",
    )
    assert spend["familio"].cancelled.runs == 1
    assert (spend["familio"].gateway_reported, spend["familio"].harness_reported) == (True, False)
    assert (spend["quiet"].gateway, spend["quiet"].harness, spend["quiet"].runs) == ("0", "0", 0)
    assert spend["quiet"].cancelled.runs == 0
    assert spend["quiet"].subscription is None


@pytest.mark.parametrize(
    ("sets", "expected"),
    [
        ([(0, True), (0, None)], True),
        ([(0, False), (1, False)], False),
        ([(0, False), (1, None)], None),
    ],
)
def test_a_projects_flag_follows_its_months_runs(
    sets: list[tuple[int, bool | None]], expected: bool | None
) -> None:
    project = a_project("p")
    runs = [a_run(project), a_run(project)]
    world = World([project], runs)
    for index, flag in sets:
        world.fact_sets.sets.append(a_set(runs[index], flag))

    [item] = spend_this_month(world.ports)

    assert item.subscription is expected


def test_the_month_begins_at_the_first_utc_instant() -> None:
    project = a_project("p")
    edge = a_run(project, started_at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    world = World([project], [edge])

    [item] = spend_this_month(world.ports)

    assert item.runs == 1


def test_project_runs_lists_newest_first_with_what_the_table_shows() -> None:
    project = a_project("p")
    old = a_run(project, created_at=THIS_MONTH, label="old", status="running", ended_at=None)
    new = a_run(
        project,
        created_at=THIS_MONTH + timedelta(days=1),
        label="new",
        label_set_by_operator=True,
        gateway_spend_usd=Decimal("15.35"),
        harness_spend_usd=Decimal("16.01"),
    )
    world = World([project], [old, new])
    world.records.rows.append(
        RunRepositoryRecord(
            id=new_id(),
            run_id=new.id,
            path=".",
            remote_url="u",
            base_branch="main",
            branch="feat/x",
        )
    )
    world.versions.add(
        ResultVersion(
            id=new_id(), run_id=new.id, n=2, calculated_at=NOW, entry_point=("manual",), methods=()
        ),
        [],
    )
    world.fact_sets.sets.append(a_set(new, True))

    first, second = project_runs(world.ports, project.id)

    assert [first.label, second.label] == ["new", "old"]
    assert (first.status, first.selectable, first.label_set_by_operator) == ("done", True, True)
    assert (first.template_name, first.template_version) == ("initiative-hub", 3)
    assert (first.harness, first.base_branch, first.branch) == ("claude", "main", "feat/x")
    assert (first.gateway, first.harness_spend) == ("15.35", "16.01")
    assert (first.latest_version, first.subscription, first.wall_clock_seconds) == (2, True, 90)
    assert (second.selectable, second.latest_version, second.branch) == (False, None, None)
    assert second.wall_clock_seconds == int((NOW - THIS_MONTH).total_seconds())
    assert second.subscription is None


@pytest.mark.parametrize(
    "status", ["done", "failed", "cancelled", "queued", "running", "needs_you"]
)
def test_only_ended_runs_are_selectable(status: str) -> None:
    project = a_project("p")
    world = World([project], [a_run(project, status=status)])

    [item] = project_runs(world.ports, project.id)

    assert item.selectable is (status in {"done", "failed", "cancelled"})


def test_a_run_that_never_started_has_no_wall_clock_and_unnamed_inputs_read_null() -> None:
    project = a_project("p")
    world = World(
        [project], [a_run(project, started_at=None, status="queued", inputs={"harness": 3})]
    )

    [item] = project_runs(world.ports, project.id)

    assert (item.wall_clock_seconds, item.harness, item.base_branch) == (None, None, None)


def test_an_unknown_project_is_not_found() -> None:
    with pytest.raises(NotFound):
        project_runs(World([], []).ports, UUID(int=9))
