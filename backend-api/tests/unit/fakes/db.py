"""In-memory `UnitOfWork` — the one fake for that port (AD-18). Reuse it; do not write another.

It holds no data: repositories and their entities arrive with the stories that need them,
and each will get its own fake beside this one. What this fake exists to record is the
transaction boundary — whether a use case committed, rolled back, and in what order — so a
test can assert "nothing was persisted" without a database.
"""

from __future__ import annotations

from types import TracebackType


class FakeUnitOfWork:
    """A unit of work that records its calls instead of talking to a database."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.calls: list[str] = []
        self._entered = False

    def __enter__(self) -> FakeUnitOfWork:
        # mirrors the adapter, where a second entry would orphan the first session
        if self._entered:
            raise RuntimeError("the unit of work is already open: it cannot be entered twice")
        self._entered = True
        self.calls.append("enter")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # mirrors the adapter: leaving the block discards whatever was not committed
        if not self.committed:
            self.rollback()
        self._entered = False
        self.calls.append("exit")

    def commit(self) -> None:
        self._require_open("commit")
        self.committed = True
        self.calls.append("commit")

    def rollback(self) -> None:
        self._require_open("rollback")
        self.rolled_back = True
        self.calls.append("rollback")

    def _require_open(self, action: str) -> None:
        if not self._entered:
            raise RuntimeError(f"{action} outside the unit of work: it was not entered")
