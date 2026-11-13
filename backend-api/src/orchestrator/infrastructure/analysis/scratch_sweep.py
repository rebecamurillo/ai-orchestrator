"""Remove the scratch folders an analysis left when the process died before its own cleanup.

Only UUID-named direct children of `{WORK_DIR}/analysis` are removed; a symlink is never
followed or removed, and nothing outside that folder is touched.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

ANALYSIS_DIRECTORY = "analysis"


def _is_uuid(name: str) -> bool:
    try:
        UUID(name)
    except ValueError:
        return False
    return True


def sweep_analysis_scratch(work_dir: str | None) -> None:
    if work_dir is None or not work_dir.strip():
        log.warning("analysis scratch not swept: WORK_DIR is not set")
        return
    folder = Path(work_dir) / ANALYSIS_DIRECTORY
    root = Path(work_dir).resolve()
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        log.warning("analysis scratch not swept: the folder is outside WORK_DIR", path=str(folder))
        return
    if not folder.is_dir():
        return
    for child in folder.iterdir():
        if child.is_symlink() or not _is_uuid(child.name):
            continue
        # A leftover that cannot be removed must never stop the engine from starting.
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError as error:
            log.warning("analysis scratch not removed", path=str(child), error=str(error))
