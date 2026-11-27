"""`FsStepLog`: the `StepLog` adapter, on the container's plain filesystem (AD-40)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from orchestrator.infrastructure.redact import redact


class FsStepLog:
    def __init__(self, work_dir: str, secrets: Sequence[str] = ()) -> None:
        self._work_dir = work_dir
        self._secrets = tuple(s for s in secrets if s)

    def write(self, run_id: UUID, seq: int, n: int, lines: Sequence[str]) -> str:
        path = Path(self._work_dir) / "logs" / str(run_id) / f"{seq:03d}-{n}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(f"{self._scrub(line)}\n" for line in lines)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _scrub(self, line: str) -> str:
        for secret in self._secrets:
            line = redact(line, secret)
        return line
