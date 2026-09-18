"""The `LogReader` port (SPEC CAP-12): the last lines of one attempt's log file.

A row's `latest.log_tail` (Run detail, 4.12) reads an attempt's `log_path` back — the file
`ProcessRunner.start` appends stdout and stderr into (`domain/ports/process.py`). That file
lives on the container's plain filesystem, outside any Repository worktree, so this is
deliberately **not** the `Workspace` port: `Workspace` scopes reads and writes to one Run's
checked-out tree (AD-14), and an attempt log is neither read nor written through it today.
A second, narrower port for a second kind of file is the ports-first rule working as
intended, not a gap in `Workspace`.

`tail` takes the path as a plain `str | None` — `Attempt.log_path` is exactly that — rather
than a `Path`, so a pure builder in `application/` can call it without importing `pathlib`
error types it would otherwise have to catch.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LogReader(Protocol):
    """Reads the last lines of a log file, or answers `[]` for one that is not there."""

    def tail(self, path: str | None, n: int) -> list[str]:
        """The last `n` lines of the file at `path`, oldest first; `[]` if `path` is
        `None` or names a file that does not exist."""
        ...

    def read_from(self, path: str, cursor: int, limit: int) -> tuple[list[str], int, bool] | None:
        """Up to `limit` complete lines starting at byte `cursor`, oldest first.

        Returns `(lines, next_cursor, eof)` where `next_cursor` is the byte offset
        immediately after the last `\\n` in the returned set, and `eof` is `True`
        when no more bytes follow. An incomplete trailing line (no `\\n`) is never
        returned — this keeps paging deterministic for pollers.

        Returns `None` when `path` is non-null but the file cannot be opened
        (`OSError`), signalling that the log was garbage-collected.
        """
        ...

    def read_raw(self, path: str) -> bytes | None:
        """The full raw content of the file at `path`, or `None` if it cannot be
        opened (`OSError`) — same GC'd signal as `read_from`."""
        ...
