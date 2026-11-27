"""The paged log of one attempt and the state that says why it is empty or gone (AD-40).

Pure: the file is read through the `LogReader` port, the attempt through its repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.logs import LogReader
from orchestrator.domain.ports.repositories import AttemptRepository

LogState = Literal["text", "no_output", "removed"]

NO_LOG_REASON = "no log was recorded for this attempt"
REMOVED_LINE = "log no longer on disk"


@dataclass(frozen=True)
class LogPage:
    lines: list[str]
    next_cursor: int
    eof: bool
    state: LogState
    removed_at: datetime | None = None
    reason: str | None = None


def read_log_page(  # noqa: PLR0913
    attempts: AttemptRepository,
    logs: LogReader,
    run_id: UUID,
    attempt_id: UUID,
    *,
    cursor: int,
    limit: int,
) -> LogPage:
    """One page of the attempt's log; `NotFound` when the attempt is not in this Run."""
    attempt = attempts.get(attempt_id)
    if attempt is None or attempt.run_id != run_id:
        raise NotFound("No attempt with that id in this Run.")
    if attempt.log_path is None:
        return LogPage(lines=[], next_cursor=0, eof=True, state="no_output", reason=NO_LOG_REASON)
    result = logs.read_from(attempt.log_path, cursor, limit)
    if result is None:
        # A stamped attempt is gone even if it was never closed (a crash left `ended_at` null).
        if attempt.ended_at is None and attempt.log_removed_at is None:
            return LogPage(lines=[], next_cursor=cursor, eof=False, state="text")
        return LogPage(
            lines=[REMOVED_LINE],
            next_cursor=0,
            eof=True,
            state="removed",
            removed_at=attempt.log_removed_at,
        )
    lines, next_cursor, eof = result
    if cursor == 0 and not lines and eof and attempt.ended_at is not None:
        return LogPage(lines=[], next_cursor=next_cursor, eof=True, state="no_output")
    return LogPage(lines=lines, next_cursor=next_cursor, eof=eof, state="text")
