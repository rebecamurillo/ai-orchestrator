"""`trajectory_export` (SPEC CAP-6, AD-19, FR-32 export): a Project's stored trajectories,
newest first, as `GET /projects/{id}/trajectories.jsonl` streams them, and the count
`GET /projects/{id}` embeds beside *Export trajectories* (UX-DR12).

Nothing here writes. `record_trajectory` (5.9) is the only writer of a `trajectory` row
(AD-19); this module only reads what `TrajectoryRepository.list_for_project` already
returns, through the port's own two methods — `add` and `list_for_project`, and no third
one (`domain/ports/trajectories.py`'s own docstring, and
`test_trajectory_repository_adapter.py::test_the_adapter_has_no_way_to_change_or_delete_a_trajectory`,
which pins the adapter's public methods to exactly that pair). `trajectory_count` is
therefore `len(list_for_project(...))` rather than a query of its own, and `prepare_export`
hands the router the whole ordered list rather than a cursor: the router's own generator is
what turns that list into a streamed, paged response (`api/routers/trajectories.py`) — HTTP
framing is not this layer's concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from orchestrator.domain.entities.trajectory import Trajectory
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.repositories import ProjectRepository
from orchestrator.domain.ports.trajectories import TrajectoryRepository


@dataclass(frozen=True)
class TrajectoryExportPorts:
    """What `prepare_export` reads: the Project (its slug, and whether it exists at all),
    the stored trajectories, and a clock for the filename's date."""

    projects: ProjectRepository
    trajectories: TrajectoryRepository
    clock: Clock


def trajectory_count(trajectories: TrajectoryRepository | None, project_id: UUID) -> int:
    """How many trajectories a Project has stored — `GET /projects/{id}`'s own
    `trajectory_count` (UX-DR12, `api/schemas/projects.py`).

    `None` when the route this feeds is wired without a trajectories port
    (`api/providers_trajectories.py::trajectory_repository`'s own docstring says when: a
    frozen test harness that predates this field, never a production gap) answers `0`, the
    same precedent `embedded_repositories`/`embedded_runs` set for their own optional ports.
    """
    if trajectories is None:
        return 0
    return len(trajectories.list_for_project(project_id))


def export_filename(slug: str, today: date) -> str:
    """`trajectories-{slug}-{date}.jsonl` (binding rule), `date` as `YYYY-MM-DD`."""
    return f"trajectories-{slug}-{today.isoformat()}.jsonl"


def prepare_export(ports: TrajectoryExportPorts, project_id: UUID) -> tuple[str, list[Trajectory]]:
    """The filename and this Project's trajectories, newest first — `list_for_project`
    already sorts them, so nothing here re-orders.

    Raises `NotFound` for a Project this instance never stored — the endpoint's own 404. An
    empty Project answers a filename and an empty list, which the router turns into 200 with
    an empty body.
    """
    project = ports.projects.get(project_id)
    if project is None:
        raise NotFound(f"no project with id {project_id}")
    trajectories = ports.trajectories.list_for_project(project_id)
    filename = export_filename(project.slug, ports.clock.now().date())
    return filename, trajectories
