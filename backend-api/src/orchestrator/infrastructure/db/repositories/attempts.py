"""The SQLAlchemy adapter for the `AttemptRepository` port (AD-8, AD-9, AD-14).

`mark_started` and `mark_finished` write **disjoint** sets of columns, and that is the whole
reason they are two methods rather than one `update`. AD-8 requires the start half to commit
in its own unit of work before `ProcessRunner.wait`, so a backend restart mid-attempt finds
`started_at`, `start_sha`, `frozen_test_files` and `pgid` stored and can report an
interrupted attempt (FR-12) instead of losing it. Each method's constant below names exactly
the columns it writes; a value the entity carries for the *other* half never reaches the row.

Otherwise it mirrors `tests/unit/fakes/runs.py::FakeAttemptRepository`: `get_latest` is the
highest `n`, `list_for_row` is ordered by `n`, a miss is `None`, and writing an attempt the
table does not hold is a `ValueError`. The `(step_run_id, n)` duplicate the fake refuses is
refused here by the unique index.

`add` flushes before it returns, for the reason `repositories/runs.py`'s docstring gives:
this row carries foreign keys to both `run` and `step_run`, the three tables are written in
one unit of work, and no `relationship()` exists for the ORM to order the inserts by.
Flushing is not committing — the transaction stays the unit of work's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.infrastructure.db.models.run import AttemptRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

#: What `mark_started` writes: the half a restart has to find (AD-8).
STARTED_COLUMNS = ("status", "started_at", "engine_ref", "start_sha", "frozen_test_files", "pgid")

#: What `mark_finished` writes: everything the harness only knows once it has exited.
FINISHED_COLUMNS = (
    "status",
    "ended_at",
    "end_sha",
    "log_path",
    "exit_code",
    "output_ref",
    "harness",
    "model",
    "session_id",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "cost_provisional",
)


def to_entity(row: AttemptRow) -> Attempt:
    """A row as the domain entity every layer above works with."""
    return Attempt(
        id=row.id,
        run_id=row.run_id,
        step_run_id=row.step_run_id,
        n=row.n,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        engine_ref=dict(row.engine_ref),
        start_sha=row.start_sha,
        end_sha=row.end_sha,
        frozen_test_files=(None if row.frozen_test_files is None else tuple(row.frozen_test_files)),
        log_path=row.log_path,
        exit_code=row.exit_code,
        output_ref=row.output_ref,
        harness=row.harness,
        model=row.model,
        session_id=row.session_id,
        pgid=row.pgid,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        cost_usd=row.cost_usd,
        cost_provisional=row.cost_provisional,
    )


def row_values(attempt: Attempt) -> dict[str, Any]:
    """Every column of the `attempt` table, keyed by name."""
    return {
        "id": attempt.id,
        "run_id": attempt.run_id,
        "step_run_id": attempt.step_run_id,
        "n": attempt.n,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "ended_at": attempt.ended_at,
        "engine_ref": dict(attempt.engine_ref),
        "start_sha": attempt.start_sha,
        "end_sha": attempt.end_sha,
        "frozen_test_files": (
            None if attempt.frozen_test_files is None else list(attempt.frozen_test_files)
        ),
        "log_path": attempt.log_path,
        "exit_code": attempt.exit_code,
        "output_ref": attempt.output_ref,
        "harness": attempt.harness,
        "model": attempt.model,
        "session_id": attempt.session_id,
        "pgid": attempt.pgid,
        "tokens_in": attempt.tokens_in,
        "tokens_out": attempt.tokens_out,
        "cost_usd": attempt.cost_usd,
        "cost_provisional": attempt.cost_provisional,
    }


#: What `update` writes back: every column but the primary key and the two it hangs from.
MUTABLE_COLUMNS: tuple[str, ...] = tuple(
    column.name
    for column in AttemptRow.__table__.columns
    if column.name not in {"id", "run_id", "step_run_id"}
)


class SQLAlchemyAttemptRepository:
    """Stored attempts, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, attempt: Attempt) -> None:
        self._session.add(AttemptRow(**row_values(attempt)))
        # emitted now, against the `run` and `step_run` rows their adapters already flushed
        self._session.flush()

    def get_latest(self, step_run_id: UUID) -> Attempt | None:
        row = self._session.scalars(
            select(AttemptRow)
            .where(AttemptRow.step_run_id == step_run_id)
            .order_by(AttemptRow.n.desc())
        ).first()
        return None if row is None else to_entity(row)

    def list_for_row(self, step_run_id: UUID) -> list[Attempt]:
        rows = self._session.scalars(
            select(AttemptRow).where(AttemptRow.step_run_id == step_run_id).order_by(AttemptRow.n)
        ).all()
        return [to_entity(row) for row in rows]

    def mark_started(self, attempt: Attempt) -> None:
        """Write `status`, `started_at`, `engine_ref`, `start_sha`, `frozen_test_files`,
        `pgid` — and nothing the harness cannot know yet."""
        self._write(attempt, STARTED_COLUMNS)

    def mark_finished(self, attempt: Attempt) -> None:
        """Write `status`, `ended_at`, `end_sha`, `log_path`, `exit_code`, `output_ref`,
        the harness columns and the usage — never the start half again."""
        self._write(attempt, FINISHED_COLUMNS)

    def update(self, attempt: Attempt) -> None:
        self._write(attempt, MUTABLE_COLUMNS)

    def _write(self, attempt: Attempt, columns: tuple[str, ...]) -> None:
        row = self._session.get(AttemptRow, attempt.id)
        if row is None:
            raise ValueError(f"no attempt with id {attempt.id} is stored")
        values = row_values(attempt)
        for column in columns:
            setattr(row, column, values[column])
