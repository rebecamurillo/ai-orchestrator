"""One step's drawer: header, attempts, run-order frame, log state, files read and written
(AD-40 "The drawer's payload"). Pure: every read goes through a port.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from orchestrator.application.graph_schema import RunOrderFrame
from orchestrator.application.run_order import STEP_TOKENS, build_run_order
from orchestrator.application.use_cases.attempt_log import read_log_page
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat, GitHistory
from orchestrator.domain.ports.logs import LogReader
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.statuses import Gate, StepStatus

COMMIT_KIND = "git.commit"
SHA = re.compile(r"^[0-9a-f]{7,40}$")
REFS_PREFIX = "refs updated: "
REFS_TAIL_LINES = 10000


@dataclass(frozen=True)
class StepDrawerPorts:
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    logs: LogReader
    history: GitHistory


@dataclass(frozen=True)
class DrawerHeader:
    seq: int
    path: str
    label: str
    kind: str
    gate: Gate
    status: StepStatus
    token: str
    n: int | None
    started_at: datetime | None
    ended_at: datetime | None
    exit_code: int | None
    cost_usd: Decimal | None


@dataclass(frozen=True)
class DrawerAttempt:
    n: int
    status: StepStatus


@dataclass(frozen=True)
class DrawerLog:
    attempt_id: UUID | None
    state: Literal["text", "no_output", "removed", "not_run"]
    removed_at: datetime | None
    reason: str | None


@dataclass(frozen=True)
class FilesRead:
    state: Literal["not_recorded", "none"]
    paths: tuple[str, ...]


@dataclass(frozen=True)
class DrawerCommit:
    sha: str
    message: str | None


@dataclass(frozen=True)
class FilesWritten:
    state: Literal["files", "commit", "refs", "none"]
    files: tuple[FileStat, ...] = ()
    commit: DrawerCommit | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepDrawer:
    header: DrawerHeader
    attempts: tuple[DrawerAttempt, ...]
    run_order: RunOrderFrame | None
    log: DrawerLog
    files_read: FilesRead
    files_written: FilesWritten


NONE_WRITTEN = FilesWritten(state="none")


def _repo_and_prefix(run: Run, row: StepRun) -> tuple[Path | None, str]:
    if run.worktree_path is None:
        return None, ""
    workdir = str(row.with_resolved.get("workdir") or "")
    base = Path(run.worktree_path)
    return (base / workdir if workdir else base), workdir


def _prefixed(files: tuple[FileStat, ...], workdir: str) -> tuple[FileStat, ...]:
    if not workdir:
        return files
    return tuple(dataclasses.replace(f, path=f"{workdir}/{f.path}") for f in files)


def _commit_written(history: GitHistory, repo: Path, workdir: str, sha: str) -> FilesWritten:
    message = history.commit_subject(repo, sha)
    files = _prefixed(history.diff_stat(repo, f"{sha}~1", sha), workdir)
    return FilesWritten(state="commit", files=files, commit=DrawerCommit(sha, message))


def _refs_written(logs: LogReader, attempt: Attempt) -> FilesWritten:
    if attempt.log_path is None:
        return NONE_WRITTEN
    refs = tuple(
        line.removeprefix(REFS_PREFIX)
        for line in logs.tail(attempt.log_path, REFS_TAIL_LINES)
        if line.startswith(REFS_PREFIX)
    )
    return FilesWritten(state="refs", refs=refs) if refs else NONE_WRITTEN


def _git_written(
    ports: StepDrawerPorts, repo: Path, workdir: str, row: StepRun, attempt: Attempt
) -> FilesWritten | None:
    """Rules (a) and (b); `None` when neither applies."""
    if attempt.start_sha and attempt.end_sha and attempt.start_sha != attempt.end_sha:
        files = ports.history.diff_stat(repo, attempt.start_sha, attempt.end_sha)
        return FilesWritten(state="files", files=_prefixed(files, workdir))
    if row.kind == COMMIT_KIND and attempt.output_ref and SHA.match(attempt.output_ref):
        return _commit_written(ports.history, repo, workdir, attempt.output_ref)
    return None


def _files_written(
    ports: StepDrawerPorts, run: Run, row: StepRun, attempt: Attempt | None
) -> FilesWritten:
    if attempt is None:
        return NONE_WRITTEN
    repo, workdir = _repo_and_prefix(run, row)
    if repo is not None:
        try:
            written = _git_written(ports, repo, workdir, row, attempt)
        except GitError:
            return NONE_WRITTEN
        if written is not None:
            return written
    return _refs_written(ports.logs, attempt)


def _log(ports: StepDrawerPorts, run_id: UUID, row: StepRun, attempt: Attempt | None) -> DrawerLog:
    if attempt is None:
        return DrawerLog(attempt_id=None, state="not_run", removed_at=None, reason=row.reason)
    page = read_log_page(ports.attempts, ports.logs, run_id, attempt.id, cursor=0, limit=1)
    return DrawerLog(
        attempt_id=attempt.id, state=page.state, removed_at=page.removed_at, reason=page.reason
    )


def _header(row: StepRun, attempt: Attempt | None) -> DrawerHeader:
    return DrawerHeader(
        seq=row.seq,
        path=row.path,
        label=row.label,
        kind=row.kind,
        gate=row.gate,
        status=row.status,
        token=STEP_TOKENS[row.status],
        n=attempt.n if attempt else None,
        started_at=attempt.started_at if attempt else None,
        ended_at=attempt.ended_at if attempt else None,
        exit_code=attempt.exit_code if attempt else None,
        cost_usd=attempt.cost_usd if attempt else None,
    )


def _pick(attempts: list[Attempt], n: int) -> Attempt | None:
    if n == 0:
        return attempts[-1] if attempts else None
    for attempt in attempts:
        if attempt.n == n:
            return attempt
    raise NotFound("No such Run, step or attempt.")


def step_drawer(ports: StepDrawerPorts, run_id: UUID, seq: int, n: int) -> StepDrawer:
    """`n = 0` is the row's latest attempt; `NotFound` for an unknown Run, seq or `n`."""
    run = ports.runs.get(run_id)
    row = ports.steps.get_by_seq(run_id, seq) if run is not None else None
    if run is None or row is None:
        raise NotFound("No such Run, step or attempt.")
    attempts = sorted(ports.attempts.list_for_row(row.id), key=lambda a: a.n)
    attempt = _pick(attempts, n)
    frames = build_run_order(ports.steps.list_for_run(run_id))
    return StepDrawer(
        header=_header(row, attempt),
        attempts=tuple(DrawerAttempt(a.n, a.status) for a in attempts),
        run_order=next((f for f in frames if any(r.seq == seq for r in f.rows)), None),
        log=_log(ports, run_id, row, attempt),
        files_read=FilesRead("not_recorded" if attempt else "none", ()),
        files_written=_files_written(ports, run, row, attempt),
    )
