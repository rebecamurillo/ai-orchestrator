"""Recording what a Run did to each repository and which commits the orchestrator made.

A side record (AGENTS.md "Data capture"): nothing here decides a status, a route or a park.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import structlog

from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.run_records import ROOT_PATH, RunRepositoryRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.run_records import RunCommitRepository, RunRepositoryRecords
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.statuses import TERMINAL_RUN

log = structlog.get_logger(__name__)

GITMODULES = ".gitmodules"
RECORD_FAILED = "run record failed"
SECTION = re.compile(r'^\s*\[submodule\s+"[^"]*"\]\s*$')
KEY_VALUE = re.compile(r"^\s*(\w+)\s*=\s*(.*?)\s*$")


@dataclass(frozen=True)
class RecordPorts:
    """What recording reaches: both repositories and the unit of work that commits them."""

    repositories: RunRepositoryRecords
    commits: RunCommitRepository
    uow: UnitOfWork


RecordWrites = Callable[[], AbstractContextManager[RecordPorts]]


def submodule_url(gitmodules: str | None, workdir: str, superproject_url: str) -> str:
    """The URL `.gitmodules` names for `workdir`, resolved against the superproject's when
    relative; `""` when there is none."""
    wanted = str(PurePosixPath(workdir))
    for section in _sections(gitmodules or ""):
        path, url = section.get("path"), section.get("url")
        if path is not None and url and str(PurePosixPath(path)) == wanted:
            return _resolve(url, superproject_url)
    return ""


def _sections(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for line in text.splitlines():
        if SECTION.match(line):
            sections.append({})
            continue
        found = KEY_VALUE.match(line)
        if found and sections:
            sections[-1][found.group(1)] = found.group(2)
    return sections


def _resolve(url: str, superproject: str) -> str:
    if not url.startswith(("./", "../")):
        return url
    base = superproject.rstrip("/")
    while url.startswith(("./", "../")):
        if url.startswith("./"):
            url = url[2:]
            continue
        url = url[3:]
        base = _parent(base)
    return f"{base}{url}" if base.endswith(":") else f"{base}/{url}"


def _parent(base: str) -> str:
    slash = base.rfind("/")
    if slash >= 0:
        return base[:slash]
    return base[: base.rfind(":") + 1]


def heads_at_end(git: Git, records: RunRepositoryRecords, run: Run) -> None:
    """Each recorded repository's local HEAD when the Run ended; a tree that will not answer
    leaves its row `NULL`."""
    if not run.worktree_path:
        return
    for record in records.list_for_run(run.id):
        tree = Path(run.worktree_path)
        if record.path != ROOT_PATH:
            tree = tree / record.path
        try:
            sha = git.head_sha(tree)
        except GitError:
            continue
        if sha is not None:
            records.set_head_local_at_end(run.id, record.path, sha)


def ended(git: Git | None, records: RunRepositoryRecords | None, before: Run, after: Run) -> None:
    """`heads_at_end` once, on the write that takes a Run from running to terminal."""
    if git is None or records is None:
        return
    if before.status not in TERMINAL_RUN and after.status in TERMINAL_RUN:
        try:
            heads_at_end(git, records, after)
        except Exception:
            log.exception(RECORD_FAILED, run_id=str(after.id))


def record_own_repository(
    records: RunRepositoryRecords | None, git: Git, run: Run, url: str, plan_tip: str | None
) -> None:
    """Write the Run's own `.` row. `plan_tip` is the base tip the plan read; a plan from a
    working branch did not read it, so it is asked once here."""
    if records is None:
        return
    base = str(run.inputs.get("base_branch") or "")
    tip = plan_tip
    if tip is None:
        try:
            found = git.ls_remote(url, base)
        except Exception:
            log.exception(RECORD_FAILED, run_id=str(run.id))
            found = None
        tip = found.sha if found is not None else ""
    record = RunRepositoryRecord(
        id=new_id(),
        run_id=run.id,
        path=ROOT_PATH,
        remote_url=url,
        base_branch=base,
        branch=str(run.inputs.get("branch") or ""),
        base_tip=tip,
    )
    records.add(record)
