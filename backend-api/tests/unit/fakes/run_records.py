"""In-memory run-record repositories and the `StepPorts.record_writes` scope over them (AD-18)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import UUID

from orchestrator.application.use_cases.run_records import RecordPorts
from orchestrator.domain.entities.run_records import RunCommit, RunRepositoryRecord
from tests.unit.fakes.db import FakeUnitOfWork


class FakeRunRepositoryRecords:
    def __init__(self, fail: Exception | None = None) -> None:
        self.rows: list[RunRepositoryRecord] = []
        self.fail = fail

    def _check(self) -> None:
        if self.fail is not None:
            raise self.fail

    def add(self, record: RunRepositoryRecord) -> bool:
        self._check()
        if self.get(record.run_id, record.path) is not None:
            return False
        self.rows.append(record)
        return True

    def get(self, run_id: UUID, path: str) -> RunRepositoryRecord | None:
        self._check()
        return next((r for r in self.rows if (r.run_id, r.path) == (run_id, path)), None)

    def list_for_run(self, run_id: UUID) -> list[RunRepositoryRecord]:
        self._check()
        return [r for r in self.rows if r.run_id == run_id]

    def _update(self, run_id: UUID, path: str, **values: str) -> None:
        self._check()
        for index, row in enumerate(self.rows):
            if (row.run_id, row.path) == (run_id, path):
                self.rows[index] = row.model_copy(update=values)

    def set_head_pushed(self, run_id: UUID, path: str, sha: str) -> None:
        self._update(run_id, path, head_pushed=sha)

    def set_head_local_at_end(self, run_id: UUID, path: str, sha: str) -> None:
        self._update(run_id, path, head_local_at_end=sha)


class FakeRunCommitRepository:
    def __init__(self, fail: Exception | None = None) -> None:
        self.commits: list[RunCommit] = []
        self.fail = fail

    def add(self, commit: RunCommit) -> None:
        if self.fail is not None:
            raise self.fail
        key = (commit.run_id, commit.path, commit.sha)
        if any((c.run_id, c.path, c.sha) == key for c in self.commits):
            return
        self.commits.append(commit)

    def list_for_run(self, run_id: UUID) -> list[RunCommit]:
        return [c for c in self.commits if c.run_id == run_id]


@dataclass
class RecordsScope:
    """Callable scope: every entry opens a fresh unit of work over one shared pair of fakes."""

    repositories: FakeRunRepositoryRecords = field(default_factory=FakeRunRepositoryRecords)
    commits: FakeRunCommitRepository = field(default_factory=FakeRunCommitRepository)
    opens: int = 0
    fail_open: bool = False
    units: list[FakeUnitOfWork] = field(default_factory=list)

    @contextmanager
    def __call__(self) -> Iterator[RecordPorts]:
        self.opens += 1
        if self.fail_open:
            raise RuntimeError("no records scope")
        unit = FakeUnitOfWork()
        self.units.append(unit)
        with unit:
            yield RecordPorts(repositories=self.repositories, commits=self.commits, uow=unit)
