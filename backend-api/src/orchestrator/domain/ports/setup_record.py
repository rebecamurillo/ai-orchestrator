"""The `SetupRecord` port: a read-only view of what the last setup run did.

The backend never writes the record (AD-29). `read` returns `None` when it is absent or
unreadable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.setup_run import SetupRun


@runtime_checkable
class SetupRecord(Protocol):
    def read(self) -> SetupRun | None: ...
