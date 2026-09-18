"""In-memory fake for the `LogReader` port (AD-18). Do not write another."""

from __future__ import annotations

_NEWLINE = ord(b"\n")  # avoids PLR2004 in byte-level comparisons


class FakeLogReader:
    """Canned lines per path, so a unit test never touches a real file.

    `raw_by_path` supplies byte content for `read_from` / `read_raw`.  A path
    absent from the dict is treated as GC'd (both methods return `None`).  A
    `None` value is also GC'd; a `bytes` value means the file exists.
    """

    def __init__(
        self,
        lines_by_path: dict[str, list[str]] | None = None,
        raw_by_path: dict[str, bytes | None] | None = None,
    ) -> None:
        self.lines_by_path = lines_by_path or {}
        self.raw_by_path: dict[str, bytes | None] = raw_by_path or {}
        self.calls: list[tuple[str | None, int]] = []

    def tail(self, path: str | None, n: int) -> list[str]:
        self.calls.append((path, n))
        if path is None:
            return []
        return self.lines_by_path.get(path, [])[-n:] if n > 0 else []

    def read_from(self, path: str, cursor: int, limit: int) -> tuple[list[str], int, bool] | None:
        """Byte-cursor paging over `raw_by_path`; `None` when path is absent or mapped to
        `None` (GC'd)."""
        if path not in self.raw_by_path or self.raw_by_path[path] is None:
            return None
        data = self.raw_by_path[path]
        assert data is not None  # narrowing — checked above
        if cursor >= len(data):
            return ([], cursor, True)
        chunk = data[cursor:]
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
                        return (all_lines[:limit], next_cursor, next_cursor >= len(data))
        next_cursor = cursor + last_nl + 1
        return (all_lines, next_cursor, next_cursor >= len(data))

    def read_raw(self, path: str) -> bytes | None:
        """The raw bytes for `path`, or `None` when GC'd."""
        return self.raw_by_path.get(path)
