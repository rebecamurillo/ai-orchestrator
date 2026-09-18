"""The SQLAlchemy adapter for the `RunRepository` port (AD-7, AD-8).

It mirrors `tests/unit/fakes/runs.py`, which every Epic 4 use-case test runs against: a
miss is `None` rather than an error, every list is newest first (`created_at` descending
with `id` descending as the tiebreak — UUIDv7 sorts by creation), and `update` refuses an id
the table does not hold. Anything this class decided that the fake did not would only ever
surface against a real database.

`row_values` is the single place a `Run` becomes columns, so `add` and `update` cannot
drift: `add` passes the whole mapping to the row constructor, `update` writes back every key
of `MUTABLE_COLUMNS`, which is `row_values` minus the primary key. The `jsonb` columns are
rebuilt rather than mutated in place — SQLAlchemy does not track a mutation inside a JSON
value, and the update would be silently dropped.

The session is the one the unit of work opened, passed in rather than looked up; see
`repositories/projects.py`'s docstring for why.

**`add` flushes, and the three sibling adapters flush for the same reason.** `run`,
`step_run`, `attempt` and `gate_record` are one aggregate written in one unit of work
(AD-8), and `attempt` carries foreign keys to both `run` and `step_run`. None of these
models declares a `relationship()` — they are plain `ForeignKey` columns — so SQLAlchemy's
unit of work has no dependency edge to sort them by, and the order of the `INSERT`s inside
a single flush is arbitrary: the `attempt` insert can reach the database before the `run`
it references, and Postgres refuses it. A use case cannot fix that itself, because the
`UnitOfWork` port has `commit` and `rollback` and no `flush`. So the caller's order is made
the database's order here: each insert method emits its statement before it returns.
Nothing below commits — the transaction is still the unit of work's, and a rollback still
discards every one of these rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.statuses import TERMINAL_RUN, RunStatus
from orchestrator.domain.values import Worktree
from orchestrator.infrastructure.db.models.run import RunRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

#: The keys of one `pinned_versions` element, named once so column and entity cannot drift.
REF_NAME_KEY = "name"
REF_VERSION_KEY = "version"

#: The keys of one `worktrees` element, for the same reason.
WORKTREE_KEYS = ("branch", "path", "created_branch", "pushed")


def to_entity(row: RunRow) -> Run:
    """A row as the domain entity every layer above works with."""
    return Run(
        id=row.id,
        project_id=row.project_id,
        repository_id=row.repository_id,
        template_name=row.template_name,
        template_version=row.template_version,
        pinned_versions=tuple(
            TemplateRef(name=ref[REF_NAME_KEY], version=ref[REF_VERSION_KEY])
            for ref in row.pinned_versions
        ),
        inputs=dict(row.inputs),
        status=row.status,
        plan_ref=row.plan_ref,
        plan_refs=dict(row.plan_refs),
        engine_ref=dict(row.engine_ref),
        budget_usd=row.budget_usd,
        spend_usd=row.spend_usd,
        spend_provisional=row.spend_provisional or False,
        manual_estimate_h=row.manual_estimate_h,
        re_review_done=row.re_review_done,
        park_kind=row.park_kind,
        park_path=row.park_path,
        park_reason=row.park_reason,
        accepted_paths=tuple(row.accepted_paths),
        worktree_path=row.worktree_path,
        worktrees=tuple(Worktree(**worktree) for worktree in row.worktrees),
        compare_urls=tuple(row.compare_urls),
        trace_id=row.trace_id,
        terminal_session=row.terminal_session,
        terminal_clean_polls=row.terminal_clean_polls,
        active_seconds=row.active_seconds,
        last_opened_at=row.last_opened_at,
        last_opened_before=row.last_opened_before,
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        worktrees_removed=row.worktrees_removed,
        partition_branch=row.partition_branch,
    )


def pinned_versions_json(run: Run) -> list[dict[str, Any]]:
    """`pinned_versions` as the `jsonb` column holds it, in the order the planner pinned."""
    return [{REF_NAME_KEY: ref.name, REF_VERSION_KEY: ref.version} for ref in run.pinned_versions]


def worktrees_json(run: Run) -> list[dict[str, Any]]:
    """`worktrees` as the `jsonb` column holds it, oldest first."""
    return [{key: getattr(worktree, key) for key in WORKTREE_KEYS} for worktree in run.worktrees]


def row_values(run: Run) -> dict[str, Any]:
    """Every column of the `run` table, keyed by name — the one entity-to-row mapping."""
    return {
        "id": run.id,
        "project_id": run.project_id,
        "repository_id": run.repository_id,
        "template_name": run.template_name,
        "template_version": run.template_version,
        "pinned_versions": pinned_versions_json(run),
        "inputs": dict(run.inputs),
        "status": run.status,
        "plan_ref": run.plan_ref,
        "plan_refs": dict(run.plan_refs),
        "engine_ref": dict(run.engine_ref),
        "budget_usd": run.budget_usd,
        "spend_usd": run.spend_usd,
        "spend_provisional": run.spend_provisional,
        "manual_estimate_h": run.manual_estimate_h,
        "re_review_done": run.re_review_done,
        "park_kind": run.park_kind,
        "park_path": run.park_path,
        "park_reason": run.park_reason,
        "accepted_paths": list(run.accepted_paths),
        "worktree_path": run.worktree_path,
        "worktrees": worktrees_json(run),
        "compare_urls": list(run.compare_urls),
        "trace_id": run.trace_id,
        "terminal_session": run.terminal_session,
        "terminal_clean_polls": run.terminal_clean_polls,
        "active_seconds": run.active_seconds,
        "last_opened_at": run.last_opened_at,
        "last_opened_before": run.last_opened_before,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "worktrees_removed": run.worktrees_removed,
        "partition_branch": run.partition_branch,
    }


#: What `update` writes back: every column but the primary key, read off the table so a
#: column added to the model cannot be left out of an update by hand.
MUTABLE_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in RunRow.__table__.columns if column.name != "id"
)


class SQLAlchemyRunRepository:
    """Stored Runs, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: Run) -> None:
        self._session.add(RunRow(**row_values(run)))
        # emitted now, so a row that references this Run cannot be inserted first
        self._session.flush()

    def get(self, run_id: UUID) -> Run | None:
        row = self._session.get(RunRow, run_id)
        return None if row is None else to_entity(row)

    def update(self, run: Run) -> None:
        row = self._session.get(RunRow, run.id)
        if row is None:
            raise ValueError(f"no run with id {run.id} is stored")
        values = row_values(run)
        for column in MUTABLE_COLUMNS:
            setattr(row, column, values[column])

    def list(self, *, project_id: UUID | None = None) -> list[Run]:
        statement = select(RunRow)
        if project_id is not None:
            statement = statement.where(RunRow.project_id == project_id)
        return self._read(statement)

    def list_by_status(self, status: RunStatus) -> list[Run]:
        return self._read(select(RunRow).where(RunRow.status == status))

    def list_by_repository_non_terminal(self, repository_id: UUID) -> list[Run]:
        return self._read(
            select(RunRow).where(
                RunRow.repository_id == repository_id,
                RunRow.status.not_in(sorted(TERMINAL_RUN)),
            )
        )

    def _read(self, statement: Any) -> list[Run]:
        """Every list is newest first; the id breaks a tie within one millisecond."""
        rows = self._session.scalars(
            statement.order_by(RunRow.created_at.desc(), RunRow.id.desc())
        ).all()
        return [to_entity(row) for row in rows]
