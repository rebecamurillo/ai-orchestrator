"""A `read` event round-trips through the fact repository (story 6, AC7)."""

from __future__ import annotations

from orchestrator.domain.entities.facts import AttemptFacts, EventFact
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.facts import EventFactRow
from orchestrator.infrastructure.db.repositories.facts import SQLAlchemyFactSetRepository
from tests.unit.test_fact_repository_adapter import NOW, RecordingSession, a_set


def test_add_stores_a_read_event_row() -> None:
    session = RecordingSession(returned=new_id())
    facts = AttemptFacts(events=(EventFact(at=NOW, conversation="main", kind="read", path="a.py"),))

    SQLAlchemyFactSetRepository(session).add(a_set(), facts)  # type: ignore[arg-type]

    rows = [r for r in session.added if isinstance(r, EventFactRow)]
    assert [(r.kind, r.path) for r in rows] == [("read", "a.py")]


def test_rows_reads_a_read_event_back() -> None:
    stored = EventFactRow(
        id=new_id(),
        fact_set_id=new_id(),
        at=NOW,
        conversation="main",
        kind="read",
        path="a.py",
        command=None,
        exit_code=None,
    )
    session = RecordingSession(selected={EventFactRow: [stored]})

    facts = SQLAlchemyFactSetRepository(session).rows(new_id())  # type: ignore[arg-type]

    assert facts.events == (EventFact(at=NOW, conversation="main", kind="read", path="a.py"),)
