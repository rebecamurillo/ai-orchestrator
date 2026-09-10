"""The in-memory fake for the `HistoryQuery` port (AD-18, story 7-5). Do not write another.

It holds `HistoryEntry` values — attempt, row, Run and Project name already joined — and
answers `list_attempts` the way `infrastructure/db/repositories/history.py` answers it over
Postgres: the same filters, the same `started_at desc, attempt_id desc` order, the same
keyset window, and the same `limit`. A fake that ordered differently would let
`application/use_cases/history.py` pass its tests and paginate wrongly against the real
table, which is the failure `tests/unit/fakes/runs.py`'s own docstring describes for the
four Run repositories.

An attempt that has never started carries no `started_at`, so it has no place in an order
keyed on one and is not a row of the history: `add` refuses it here, and the adapter's own
`WHERE started_at IS NOT NULL` drops it there.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.domain.ports.history import HistoryEntry, HistoryQuerySpec

#: What an entry with no `started_at` sorts under. `add` refuses to store one, so this is
#: only ever reached by a test that pushed one straight onto `entries` to prove what
#: `list_history` does with an entry the port should never have answered.
_UNSTARTED = datetime.min.replace(tzinfo=UTC)


class FakeHistoryQuery:
    """Joined history entries in a list, answered in the order the index would give."""

    def __init__(self, entries: list[HistoryEntry] | None = None) -> None:
        self.entries: list[HistoryEntry] = []
        self.calls: list[HistoryQuerySpec] = []
        for entry in entries or []:
            self.add(entry)

    def add(self, entry: HistoryEntry) -> None:
        if entry.attempt.started_at is None:
            raise ValueError(f"attempt {entry.attempt.id} never started: it has no history row")
        self.entries.append(entry)

    def list_attempts(self, spec: HistoryQuerySpec) -> list[HistoryEntry]:
        self.calls.append(spec)
        matching = [entry for entry in self.entries if _matches(entry, spec)]
        matching.sort(key=_order_key, reverse=True)
        if spec.after is not None:
            key = (spec.after.started_at, spec.after.attempt_id)
            matching = [entry for entry in matching if _order_key(entry) < key]
        return matching[: spec.limit]


def _order_key(entry: HistoryEntry) -> tuple[datetime, object]:
    """`(started_at, attempt_id)` — the keyset the cursor encodes and the index orders by."""
    return (entry.attempt.started_at or _UNSTARTED, entry.attempt.id)


def _matches(entry: HistoryEntry, spec: HistoryQuerySpec) -> bool:
    if spec.project_id is not None and entry.run.project_id != spec.project_id:
        return False
    if spec.statuses is not None and entry.attempt.status not in spec.statuses:
        return False
    return not (spec.harness is not None and entry.attempt.harness != spec.harness)
