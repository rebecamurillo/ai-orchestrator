"""In-memory fake for the `LogReader` port (AD-18). Do not write another."""

from __future__ import annotations


class FakeLogReader:
    """Canned lines per path, so a unit test never touches a real file."""

    def __init__(self, lines_by_path: dict[str, list[str]] | None = None) -> None:
        self.lines_by_path = lines_by_path or {}
        self.calls: list[tuple[str | None, int]] = []

    def tail(self, path: str | None, n: int) -> list[str]:
        self.calls.append((path, n))
        if path is None:
            return []
        return self.lines_by_path.get(path, [])[-n:] if n > 0 else []
