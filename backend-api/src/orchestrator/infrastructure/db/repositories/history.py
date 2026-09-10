"""The SQLAlchemy adapter for the `HistoryQuery` port (story 7-5, SPEC CAP-5, FR-25).

One statement, four tables, one page. The joins are inner joins because every column the
row prints has a `NOT NULL` foreign key behind it: an attempt always has a `step_run`, a
`step_run` always has a `run`, and a `run` always has a `project`. There is no outer-join
case to widen for.

**The order is the index, and the cursor is the same tuple.** `ORDER BY started_at DESC,
id DESC` with `WHERE (started_at, id) < (:started_at, :id)` is a keyset window: Postgres
compares the row constructor lexicographically, which is exactly the order the `ORDER BY`
imposes, so the window is always "everything strictly after the row the cursor names" no
matter how many attempts have started since. An `OFFSET` would re-slide every later page as
new attempts land above it, which on this table happens continuously.

`started_at IS NOT NULL` is not a filter the caller asked for: it is the port's own rule
(`domain/ports/history.py`). An attempt is written in two halves (AD-8) and the row exists
before `mark_started` fills that column in, so without this predicate a page would carry
rows with no time and no order.

The entities come back through the three `to_entity` functions the row repositories already
own, so this module states no mapping of its own and cannot drift from theirs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, select, tuple_

from orchestrator.domain.ports.history import HistoryEntry, HistoryQuerySpec
from orchestrator.infrastructure.db.models.project import ProjectRow
from orchestrator.infrastructure.db.models.run import AttemptRow, RunRow, StepRunRow
from orchestrator.infrastructure.db.repositories.attempts import to_entity as attempt_entity
from orchestrator.infrastructure.db.repositories.runs import to_entity as run_entity
from orchestrator.infrastructure.db.repositories.step_runs import to_entity as step_entity

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


class SQLAlchemyHistoryQuery:
    """One page of executed attempts, over one open session. Reads; writes nothing."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_attempts(self, spec: HistoryQuerySpec) -> list[HistoryEntry]:
        rows = self._session.execute(_statement(spec)).all()
        return [
            HistoryEntry(
                attempt=attempt_entity(attempt),
                step=step_entity(step),
                run=run_entity(run),
                project_name=project_name,
            )
            for attempt, step, run, project_name in rows
        ]


def _statement(spec: HistoryQuerySpec) -> Select[Any]:
    """The one statement: the join, the port's own rule, the filters, the window, the page."""
    statement = (
        select(AttemptRow, StepRunRow, RunRow, ProjectRow.name)
        .join(StepRunRow, AttemptRow.step_run_id == StepRunRow.id)
        .join(RunRow, AttemptRow.run_id == RunRow.id)
        .join(ProjectRow, RunRow.project_id == ProjectRow.id)
        .where(AttemptRow.started_at.is_not(None))
    )
    if spec.project_id is not None:
        statement = statement.where(RunRow.project_id == spec.project_id)
    if spec.statuses is not None:
        statement = statement.where(AttemptRow.status.in_(spec.statuses))
    if spec.harness is not None:
        statement = statement.where(AttemptRow.harness == spec.harness)
    if spec.after is not None:
        statement = statement.where(
            tuple_(AttemptRow.started_at, AttemptRow.id)
            < tuple_(spec.after.started_at, spec.after.attempt_id)
        )
    return statement.order_by(AttemptRow.started_at.desc(), AttemptRow.id.desc()).limit(spec.limit)
