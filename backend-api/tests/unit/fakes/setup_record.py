"""In-memory `SetupRecord` — the one fake for that port (AD-18). Do not write another.

`setup_run(**overrides)` builds a valid C6 record; `reads` counts how often `read()` ran.
"""

from __future__ import annotations

from typing import Any

from orchestrator.domain.entities.setup_run import SetupRun
from orchestrator.domain.ports.setup_record import SetupRecord


def setup_run(**overrides: Any) -> SetupRun:
    data: dict[str, Any] = {
        "at": "2026-11-11T08:00:00Z",
        "trigger": "install",
        "release": "1.0.0-beta.4",
        "bmad": {"choice": "installed", "version": "6.13.0", "ok": True},
        "scripts": [
            {"name": "10-copy.sh", "exit": 0, "ok": True, "clashes": [], "seconds": 1.5, "log": "l"}
        ],
        "operator": {"ok": True},
        "catalog": {"claude": 12, "codex": 9, "opencode": 7},
    }
    data.update(overrides)
    return SetupRun.model_validate(data)


class FakeSetupRecord:
    def __init__(self, run: SetupRun | None = None) -> None:
        self._run = run
        self.reads = 0

    def read(self) -> SetupRun | None:
        self.reads += 1
        return self._run


assert isinstance(FakeSetupRecord(), SetupRecord)
