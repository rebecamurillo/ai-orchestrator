"""`RealLogReader`: the last lines of an attempt's log file, read straight off disk.

Plain file I/O, deliberately outside `Workspace` (see `domain/ports/logs.py`'s own
docstring for why). Reading the whole file and slicing its last `n` lines is the simplest
correct implementation for the sizes these logs reach in this release (a single Run's
attempt, not a multi-gigabyte stream); nothing here claims to scale past that.
"""

from __future__ import annotations

from pathlib import Path

_NEWLINE = ord(b"\n")  # 10 — avoids PLR2004 "magic value" in byte comparisons


class RealLogReader:
    """Reads `Attempt.log_path` back for the Run detail's `StepRow.latest.log_tail`."""

    def tail(self, path: str | None, n: int) -> list[str]:
        """The last `n` lines of the file at `path`; `[]` when there is nothing to read.

        `is_file()` and the read are two calls, not one: a log `worktree_gc` (SPEC CAP-11)
        sweeps between them would otherwise turn a routine detail read into a 500 rather
        than the same `[]` a request that arrived a moment later would get.
        """
        if path is None:
            return []
        file = Path(path)
        try:
            if not file.is_file():
                return []
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return lines[-n:] if n > 0 else []

    def read_from(self, path: str, cursor: int, limit: int) -> tuple[list[str], int, bool] | None:
        """Up to `limit` complete lines from byte `cursor`; `None` on `OSError` (GC'd).

        Opens in binary mode and seeks to `cursor`, so an O(1) seek serves each
        poll regardless of how large the file has grown. Incomplete trailing lines
        (no `\\n` yet) are withheld, keeping the byte cursor deterministic.
        """
        try:
            with Path(path).open("rb") as f:
                f.seek(cursor)
                chunk = f.read()
        except OSError:
            return None
        total_size = cursor + len(chunk)
        if not chunk:
            return ([], cursor, True)
        last_nl = chunk.rfind(b"\n")
        if last_nl == -1:
            return ([], cursor, False)
        complete = chunk[: last_nl + 1]
        all_lines = complete.decode("utf-8", errors="replace").splitlines()
        if len(all_lines) > limit:
            count = 0
            for i, byte_val in enumerate(complete):
                if byte_val == _NEWLINE:
                    count += 1
                    if count == limit:
                        next_cursor = cursor + i + 1
                        return (all_lines[:limit], next_cursor, next_cursor >= total_size)
        next_cursor = cursor + last_nl + 1
        return (all_lines, next_cursor, next_cursor >= total_size)

    def read_raw(self, path: str) -> bytes | None:
        """The full raw content of the file, or `None` on `OSError` (GC'd)."""
        try:
            return Path(path).read_bytes()
        except OSError:
            return None
