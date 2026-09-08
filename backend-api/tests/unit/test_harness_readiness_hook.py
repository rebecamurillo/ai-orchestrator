"""`infrastructure/db/harness_readiness.py`: `evaluate` wired to a session of its own.

The rule itself is `tests/unit/application/test_harness_readiness_evaluate.py`'s; what is
asserted here, the way `test_run_finished_hook.py` does for its own sibling module, is the
wiring: which adapter reads which session, and that the session is closed on every path.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db import harness_readiness as module
from orchestrator.infrastructure.db.harness_readiness import readiness_evaluate_hook

WORK_DIR = Path("/work")


class RecordingSession:
    """A session that records only that it was closed — no SQL runs here."""

    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _Answering:
    def __init__(self, answer: object = None) -> None:
        self.answer = answer

    def get(self, _id: UUID) -> object:
        return self.answer

    def get_latest(self, _id: UUID) -> object:
        return self.answer

    def list_for_run(self, _id: UUID) -> list[object]:
        return []

    def update(self, value: object) -> None:
        pass


def wire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every repository `evaluate` reads answers `None`/`[]`, so it returns `None` fast —
    this module's own wiring is the subject, not `evaluate`'s rules."""
    for name in (
        "SQLAlchemyRunRepository",
        "SQLAlchemyStepRunRepository",
        "SQLAlchemyAttemptRepository",
        "SQLAlchemyHarnessRepository",
        "SQLAlchemyProjectRepository",
        "SQLAlchemyRepositoryRepository",
    ):
        monkeypatch.setattr(module, name, lambda _s: _Answering())


def test_the_session_is_closed_even_when_there_is_nothing_to_evaluate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch)
    session = RecordingSession()

    readiness_evaluate_hook(lambda: session, None, None, None, WORK_DIR, new_id())

    assert session.closed == 1


def test_the_session_closes_even_when_evaluate_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch)

    def exploding(_session: object) -> object:
        raise RuntimeError("a repository could not be built")

    monkeypatch.setattr(module, "SQLAlchemyRunRepository", exploding)
    session = RecordingSession()

    with pytest.raises(RuntimeError, match="a repository could not be built"):
        readiness_evaluate_hook(lambda: session, None, None, None, WORK_DIR, new_id())

    assert session.closed == 1
