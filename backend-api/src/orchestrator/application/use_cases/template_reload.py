"""`reload_folder` — the folder pass on demand (SPEC CAP-5, D3).

Takes one snapshot of the operator's folder, runs `seed_folder` on it and commits. There is
no `try`: a `Conflict` from the repository propagates and the unit of work's exit rolls back.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.application.use_cases.template_folder import FolderOutcome, seed_folder
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.errors import Conflict

FOLDER_OFF = "template folder not configured"
FOLDER_MISSING = "template folder not found: "


@dataclass(frozen=True)
class FolderReload:
    """The folder path that was read and what the pass did with it."""

    folder: str
    outcome: FolderOutcome


def reload_folder(ports: TemplatePorts) -> FolderReload:
    """Re-read the operator's folder once and store what changed."""
    if ports.folders is None:
        raise Conflict(FOLDER_OFF)
    snapshot = ports.folders.operator()
    if snapshot.state == "off":
        raise Conflict(FOLDER_OFF)
    if snapshot.state == "missing":
        raise Conflict(FOLDER_MISSING + snapshot.path)
    outcome = seed_folder(ports, snapshot)
    ports.uow.commit()
    return FolderReload(snapshot.path, outcome)
