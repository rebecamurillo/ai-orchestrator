"""Response schema of `GET /runs/{run_id}/steps/{seq}/attempts/{n}/drawer` (AD-40)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.api.schemas.graph import RunOrderFrameOut
from orchestrator.application.use_cases.run_step_drawer import StepDrawer
from orchestrator.domain.ports.git_history import FileStat
from orchestrator.domain.statuses import Gate, StepStatus


class DrawerHeaderOut(BaseModel):
    seq: int
    path: str
    label: str
    kind: str
    gate: Gate
    status: StepStatus
    token: str
    n: int | None
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None
    exit_code: int | None
    cost_usd: MoneyStr | None


class DrawerAttemptOut(BaseModel):
    n: int
    status: StepStatus


class DrawerLogOut(BaseModel):
    attempt_id: UUID | None
    state: Literal["text", "no_output", "removed", "not_run"]
    removed_at: UtcTimestamp | None
    reason: str | None


class FilesReadOut(BaseModel):
    state: Literal["listed", "not_recorded", "none"]
    paths: list[str]


class FileStatOut(BaseModel):
    path: str
    added: int | None
    removed: int | None

    @classmethod
    def of(cls, stat: FileStat) -> FileStatOut:
        return cls(path=stat.path, added=stat.added, removed=stat.removed)


class DrawerCommitOut(BaseModel):
    sha: str
    message: str | None


class FilesWrittenOut(BaseModel):
    state: Literal["files", "commit", "refs", "none"]
    files: list[FileStatOut]
    commit: DrawerCommitOut | None
    refs: list[str]


class StepDrawerOut(BaseModel):
    header: DrawerHeaderOut
    attempts: list[DrawerAttemptOut]
    run_order: RunOrderFrameOut | None
    log: DrawerLogOut
    files_read: FilesReadOut
    files_written: FilesWrittenOut

    @classmethod
    def of(cls, drawer: StepDrawer) -> StepDrawerOut:
        h, w = drawer.header, drawer.files_written
        return cls(
            header=DrawerHeaderOut(**vars(h)),
            attempts=[DrawerAttemptOut(n=a.n, status=a.status) for a in drawer.attempts],
            run_order=RunOrderFrameOut.of(drawer.run_order) if drawer.run_order else None,
            log=DrawerLogOut(
                attempt_id=drawer.log.attempt_id,
                state=drawer.log.state,
                removed_at=drawer.log.removed_at,
                reason=drawer.log.reason,
            ),
            files_read=FilesReadOut(
                state=drawer.files_read.state, paths=list(drawer.files_read.paths)
            ),
            files_written=FilesWrittenOut(
                state=w.state,
                files=[FileStatOut.of(f) for f in w.files],
                commit=DrawerCommitOut(sha=w.commit.sha, message=w.commit.message)
                if w.commit
                else None,
                refs=list(w.refs),
            ),
        )
