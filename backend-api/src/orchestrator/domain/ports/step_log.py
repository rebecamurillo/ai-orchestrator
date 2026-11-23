"""The `StepLog` port (AD-40 "Writing"): one writer for every deterministic step's log.

The file lives at the path `application/steps/context.py::log_path` computes, so the
endpoint that reads an attempt's log finds it where it already looks.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class StepLog(Protocol):
    """Stores one attempt's log lines, credentials removed, and says where."""

    def write(self, run_id: UUID, seq: int, n: int, lines: Sequence[str]) -> str:
        """Replace the log of row `seq`, attempt `n`, and return its path."""
        ...
