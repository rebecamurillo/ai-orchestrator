"""The SQLAlchemy adapter for the `HarnessRepository` port (SPEC CAP-3, AD-10).

Mirrors `infrastructure/db/repositories/templates.py`: `get` answers `None` rather than
raising, and the session is the one the unit of work opened, passed in rather than looked
up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from orchestrator.domain.entities.harness import EvaluationLine, Harness
from orchestrator.infrastructure.db.models.harness import HarnessRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: HarnessRow) -> Harness:
    """A row as the domain entity every layer above works with."""
    return Harness(
        name=row.name,
        enabled=row.enabled,
        last_readiness_at=row.last_readiness_at,
        failing_check=row.failing_check,
        version_pin=row.version_pin,
        last_readiness_run_id=row.last_readiness_run_id,
        lines=tuple(EvaluationLine(**line) for line in row.lines),
    )


def _lines_json(harness: Harness) -> list[dict[str, object]]:
    """`harness.lines` as the `jsonb` column holds it, in evaluation order."""
    return [line.model_dump(mode="json") for line in harness.lines]


class SQLAlchemyHarnessRepository:
    """Stored harnesses, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, name: str) -> Harness | None:
        row = self._session.get(HarnessRow, name)
        return None if row is None else to_entity(row)

    def add(self, harness: Harness) -> None:
        self._session.add(
            HarnessRow(
                name=harness.name,
                enabled=harness.enabled,
                last_readiness_at=harness.last_readiness_at,
                failing_check=harness.failing_check,
                version_pin=harness.version_pin,
                last_readiness_run_id=harness.last_readiness_run_id,
                lines=_lines_json(harness),
            )
        )

    def update(self, harness: Harness) -> None:
        row = self._session.get(HarnessRow, harness.name)
        if row is None:
            raise ValueError(f"no harness named {harness.name!r} is stored")
        row.enabled = harness.enabled
        row.last_readiness_at = harness.last_readiness_at
        row.failing_check = harness.failing_check
        row.version_pin = harness.version_pin
        row.last_readiness_run_id = harness.last_readiness_run_id
        # rebuilt, not mutated in place: SQLAlchemy does not track a mutation inside a JSON
        # value, and the update would be silently dropped (`project.py`'s own precedent).
        row.lines = _lines_json(harness)

    def list(self) -> list[Harness]:
        rows = self._session.scalars(select(HarnessRow).order_by(HarnessRow.name)).all()
        return [to_entity(row) for row in rows]
