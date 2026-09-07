"""`RealLogReader`: the last lines of an attempt's log file, read straight off disk.

Plain file I/O, deliberately outside `Workspace` (see `domain/ports/logs.py`'s own
docstring for why). Reading the whole file and slicing its last `n` lines is the simplest
correct implementation for the sizes these logs reach in this release (a single Run's
attempt, not a multi-gigabyte stream); nothing here claims to scale past that.
"""

from __future__ import annotations

from pathlib import Path


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
