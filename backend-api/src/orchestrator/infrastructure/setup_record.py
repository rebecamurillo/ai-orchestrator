"""Filesystem adapter for `SetupRecord`: `$AGENT_HOME/.orchestrator/setup-run.json`."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import structlog
from pydantic import ValidationError

from orchestrator.domain.entities.setup_run import SetupRun

log = structlog.get_logger(__name__)

RECORD = Path(".orchestrator") / "setup-run.json"
#: The agent user can replace the record with a FIFO or `/dev/zero`; refuse anything that is
#: not a regular file of bounded size before reading it.
MAX_BYTES = 1 << 20


class FsSetupRecord:
    """Absent is `None` silently; unreadable is `None` with one warning. Never raises."""

    def __init__(self, agent_home: Path) -> None:
        self._agent_home = agent_home

    def read(self) -> SetupRun | None:
        path = self._agent_home / RECORD
        try:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError(f"not a regular file under {MAX_BYTES} bytes")
            return SetupRun.model_validate(json.loads(path.read_text()))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RecursionError, ValidationError) as exc:
            log.warning("setup record unreadable", path=str(path), error=str(exc))
            return None
