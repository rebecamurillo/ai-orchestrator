"""Repository ports for the per-repository and per-commit records of a Run."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from orchestrator.domain.entities.run_records import RunCommit, RunRepositoryRecord


class RunRepositoryRecords(Protocol):
    def add(self, record: RunRepositoryRecord) -> bool:
        """Insert when `(run_id, path)` is absent; `False` when it was already there."""
        ...

    def get(self, run_id: UUID, path: str) -> RunRepositoryRecord | None: ...

    def list_for_run(self, run_id: UUID) -> list[RunRepositoryRecord]: ...

    def set_head_pushed(self, run_id: UUID, path: str, sha: str) -> None: ...

    def set_head_local_at_end(self, run_id: UUID, path: str, sha: str) -> None: ...


class RunCommitRepository(Protocol):
    def add(self, commit: RunCommit) -> None:
        """A duplicate `(run_id, path, sha)` is ignored."""
        ...

    def list_for_run(self, run_id: UUID) -> list[RunCommit]: ...
