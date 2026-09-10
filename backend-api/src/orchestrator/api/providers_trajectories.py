"""Ports for the trajectory-reading routes (SPEC CAP-6, AD-19, FR-32 export): the count
`GET /projects/{id}` embeds beside *Export trajectories* (UX-DR12), and the export
`GET /projects/{id}/trajectories.jsonl` streams.

A module of its own, not an addition to `api/providers.py` — that module is 391/400 lines
(`test_source_limits.py`), and the split-not-trim rule (root `AGENTS.md` hard rule 6) says a
capped module gains a sibling rather than one more function. `trajectory_export_ports` opens
its own `SQLAlchemyUnitOfWork`, the same read-only shape `api/providers.py::history_ports`
uses: it writes nothing, so it needs no shared transaction with `project_ports`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers import SESSION_FACTORY, from_state
from orchestrator.application.use_cases.trajectory_export import TrajectoryExportPorts
from orchestrator.domain.ports.trajectories import TrajectoryRepository
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectRepository,
    SQLAlchemyTrajectoryRepository,
    SQLAlchemyUnitOfWork,
)


def trajectory_repository(request: Request) -> Iterator[TrajectoryRepository | None]:
    """The trajectory count `GET /projects/{id}` embeds (UX-DR12), read tolerantly the way
    `api/providers.py::git_adapter` reads its own adapter rather than through `from_state`.

    Every Project operation predates this capability, and its own frozen router test
    (`test_projects_router.py`) overrides only `project_ports` — a request built without a
    database session factory still has to serve every Project operation, so this yields
    `None` rather than raising. `trajectory_count` (`application/use_cases/
    trajectory_export.py`) reads `None` as "not wired" and answers `0`, the same precedent
    `application/use_cases/projects.py::embedded_repositories` sets for
    `ProjectPorts.repositories`. `api/providers.py` always supplies a real
    `session_factory`, so a production read still queries truthfully.
    """
    session_factory = getattr(request.app.state, SESSION_FACTORY, None)
    if session_factory is None:
        yield None
        return
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield SQLAlchemyTrajectoryRepository(uow.session)


def trajectory_export_ports(request: Request) -> Iterator[TrajectoryExportPorts]:
    """The ports `GET /projects/{id}/trajectories.jsonl` reads through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield TrajectoryExportPorts(
            projects=SQLAlchemyProjectRepository(uow.session),
            trajectories=SQLAlchemyTrajectoryRepository(uow.session),
            clock=SystemClock(),
        )
