"""SQLAlchemy adapters for the run-record ports. No delete; `add` is `ON CONFLICT DO NOTHING`."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.run_records import RunCommit, RunRepositoryRecord
from orchestrator.infrastructure.db.models.run_records import (
    RUN_COMMIT_UNIQUE,
    RUN_REPOSITORY_UNIQUE,
    RunCommitRow,
    RunRepositoryRow,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def _record(row: RunRepositoryRow) -> RunRepositoryRecord:
    return RunRepositoryRecord(
        id=row.id,
        run_id=row.run_id,
        path=row.path,
        remote_url=row.remote_url,
        base_branch=row.base_branch,
        branch=row.branch,
        base_tip=row.base_tip,
        head_pushed=row.head_pushed,
        head_local_at_end=row.head_local_at_end,
    )


def _commit(row: RunCommitRow) -> RunCommit:
    return RunCommit(
        id=row.id,
        run_id=row.run_id,
        path=row.path,
        sha=row.sha,
        made_by=row.made_by,  # type: ignore[arg-type]
        at=row.at,
    )


class SQLAlchemyRunRepositoryRecords:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: RunRepositoryRecord) -> bool:
        statement = (
            postgresql.insert(RunRepositoryRow)
            .values(**record.model_dump())
            .on_conflict_do_nothing(constraint=RUN_REPOSITORY_UNIQUE)
            .returning(RunRepositoryRow.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def get(self, run_id: UUID, path: str) -> RunRepositoryRecord | None:
        row = self._session.scalars(
            select(RunRepositoryRow).where(
                RunRepositoryRow.run_id == run_id, RunRepositoryRow.path == path
            )
        ).first()
        return _record(row) if row is not None else None

    def list_for_run(self, run_id: UUID) -> list[RunRepositoryRecord]:
        rows = self._session.scalars(
            select(RunRepositoryRow)
            .where(RunRepositoryRow.run_id == run_id)
            .order_by(RunRepositoryRow.path)
        ).all()
        return [_record(row) for row in rows]

    def set_head_pushed(self, run_id: UUID, path: str, sha: str) -> None:
        self._session.execute(
            update(RunRepositoryRow)
            .where(RunRepositoryRow.run_id == run_id, RunRepositoryRow.path == path)
            .values(head_pushed=sha)
        )

    def set_head_local_at_end(self, run_id: UUID, path: str, sha: str) -> None:
        self._session.execute(
            update(RunRepositoryRow)
            .where(RunRepositoryRow.run_id == run_id, RunRepositoryRow.path == path)
            .values(head_local_at_end=sha)
        )


class SQLAlchemyRunCommitRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, commit: RunCommit) -> None:
        self._session.execute(
            postgresql.insert(RunCommitRow)
            .values(**commit.model_dump())
            .on_conflict_do_nothing(constraint=RUN_COMMIT_UNIQUE)
        )

    def list_for_run(self, run_id: UUID) -> list[RunCommit]:
        rows = self._session.scalars(
            select(RunCommitRow).where(RunCommitRow.run_id == run_id).order_by(RunCommitRow.at)
        ).all()
        return [_commit(row) for row in rows]
