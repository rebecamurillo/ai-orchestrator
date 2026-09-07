"""`clone_check`, the daily job (SPEC CAP-11, FR-4): re-run every Repository's clone check.

The check itself is Epic 2's (`application/use_cases/clone_check.py`); this module decides
only *which* Repositories to re-check today — every one, across every Project — and logs
the outcome, one line per Repository. `run_clone_checks_for_project` already commits after
each Project's Repositories and already leaves a failed check stored as `status: failed`
(the same field `application/preflight/checks.py::clone_check_line` reads), so a Repository
whose origin went unreachable overnight blocks a *new* Run at pre-flight from the very next
read — this job writes no Run status itself (AD-8) and touches no queued or running Run.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from orchestrator.application.use_cases.clone_check import run_clone_checks_for_project
from orchestrator.application.use_cases.projects import ProjectPorts

log = structlog.get_logger(__name__)


def run_clone_check_job(ports: ProjectPorts, *, work_dir: Path, bmad_version: str) -> None:
    """Every Repository of every Project, checked and logged once."""
    for project in ports.projects.list():
        for repository in run_clone_checks_for_project(
            ports, project.id, work_dir=work_dir, bmad_version=bmad_version
        ):
            log.info(
                "clone check",
                repository_id=str(repository.id),
                status=repository.clone_check.status,
            )
