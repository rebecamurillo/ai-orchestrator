"""In-memory fake for the StepLog port (AD-18). Do not write another."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID


class FakeStepLog:
    def __init__(self, work_dir: str) -> None:
        self._work_dir = work_dir
        self.writes: list[tuple[UUID, int, int, tuple[str, ...]]] = []

    def write(self, run_id: UUID, seq: int, n: int, lines: Sequence[str]) -> str:
        self.writes.append((run_id, seq, n, tuple(lines)))
        return str(Path(self._work_dir) / "logs" / str(run_id) / f"{seq:03d}-{n}.log")
