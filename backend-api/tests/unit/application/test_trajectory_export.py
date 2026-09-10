"""`trajectory_export` (SPEC CAP-6, AD-19, FR-32 export): story 7.6's own acceptance — the
filename, the count, and the ordered list `GET /projects/{id}/trajectories.jsonl` streams.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from orchestrator.application.use_cases.trajectory_export import (
    TrajectoryExportPorts,
    export_filename,
    prepare_export,
    trajectory_count,
)
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.trajectory import GateResults, Trajectory
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.trajectories import FakeTrajectoryRepository

AT = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "my-website",
        "name": "My website",
        "context_text": "",
        "context_paths": (),
        "env_vars_enc": (),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


def a_trajectory(**overrides: object) -> Trajectory:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "epic_index": 0,
        "frame": "stories[0]",
        "gate_results": GateResults(build="liveness", verify="done", commit_guard="done"),
        "recorded_at": AT,
    }
    fields.update(overrides)
    return Trajectory(**fields)  # type: ignore[arg-type]


def test_the_filename_names_the_slug_and_the_date() -> None:
    expected = "trajectories-my-website-2026-09-10.jsonl"

    assert export_filename("my-website", date(2026, 9, 10)) == expected


def test_the_count_is_how_many_trajectories_this_project_has() -> None:
    project_id = new_id()
    owned_count = 2
    trajectories = FakeTrajectoryRepository(
        [a_trajectory(project_id=project_id), a_trajectory(project_id=project_id), a_trajectory()]
    )

    assert trajectory_count(trajectories, project_id) == owned_count


def test_the_count_is_zero_for_a_project_with_none() -> None:
    assert trajectory_count(FakeTrajectoryRepository(), new_id()) == 0


def test_the_count_is_zero_when_the_port_is_not_wired() -> None:
    """`api/providers_trajectories.py::trajectory_repository` answers `None` for a request
    built without a database session factory — a frozen test harness that predates this
    field, never a production gap."""
    assert trajectory_count(None, new_id()) == 0


def _ports(
    *, projects: FakeProjectRepository, trajectories: FakeTrajectoryRepository
) -> TrajectoryExportPorts:
    return TrajectoryExportPorts(projects=projects, trajectories=trajectories, clock=FakeClock(AT))


def test_an_unknown_project_is_not_found() -> None:
    ports = _ports(projects=FakeProjectRepository(), trajectories=FakeTrajectoryRepository())

    with pytest.raises(NotFound):
        prepare_export(ports, new_id())


def test_an_empty_project_answers_a_filename_and_no_rows() -> None:
    project = a_project()
    ports = _ports(
        projects=FakeProjectRepository([project]), trajectories=FakeTrajectoryRepository()
    )

    filename, rows = prepare_export(ports, project.id)

    assert filename == f"trajectories-my-website-{AT.date().isoformat()}.jsonl"
    assert rows == []


def test_three_trajectories_arrive_newest_first() -> None:
    project = a_project()
    older = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 8, tzinfo=UTC))
    newer = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 9, tzinfo=UTC))
    newest = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 10, tzinfo=UTC))
    ports = _ports(
        projects=FakeProjectRepository([project]),
        trajectories=FakeTrajectoryRepository([older, newest, newer]),
    )

    _filename, rows = prepare_export(ports, project.id)

    assert [row.id for row in rows] == [newest.id, newer.id, older.id]


def test_a_trajectory_of_another_project_is_never_included() -> None:
    project = a_project()
    other = a_project(id=new_id(), slug="other", name="Other")
    mine = a_trajectory(project_id=project.id)
    theirs = a_trajectory(project_id=other.id)
    ports = _ports(
        projects=FakeProjectRepository([project, other]),
        trajectories=FakeTrajectoryRepository([mine, theirs]),
    )

    _filename, rows = prepare_export(ports, project.id)

    assert [row.id for row in rows] == [mine.id]
