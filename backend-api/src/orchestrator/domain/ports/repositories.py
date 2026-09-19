"""The repository ports: how a use case reaches stored entities without naming a database.

One `Protocol` per entity. A repository takes and returns domain entities, never rows and
never a session: `application/` may not import `sqlalchemy` (AD-2), and a use case written
against these methods runs unchanged over the in-memory fakes in `tests/unit/fakes/` and
over the SQLAlchemy adapters in `infrastructure/db/repositories/`.

Reads return `None` for "not stored"; deciding that a missing Project is a `NotFound` is a
rule, and rules live in `application/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import RunStatus


@runtime_checkable
class ProjectRepository(Protocol):
    """Stored Projects, by id and by slug."""

    def add(self, project: Project) -> None:
        """Store a Project that does not exist yet."""
        ...

    def get(self, project_id: UUID) -> Project | None:
        """The Project with this id, or `None`."""
        ...

    def get_by_slug(self, slug: str) -> Project | None:
        """The Project with this slug, or `None` — the slug is unique per instance."""
        ...

    def list(self) -> list[Project]:
        """Every stored Project, ordered by `name`."""
        ...

    def update(self, project: Project) -> None:
        """Replace the stored Project with this one, matched on its id."""
        ...


@runtime_checkable
class RepositoryRepository(Protocol):
    """Stored Repositories, each scoped to the Project it is nested under."""

    def add(self, repository: Repository) -> None:
        """Store a Repository that does not exist yet."""
        ...

    def get(self, repository_id: UUID) -> Repository | None:
        """The Repository with this id, or `None`."""
        ...

    def list_by_project(self, project_id: UUID) -> list[Repository]:
        """Every Repository stored under this Project, ordered by creation time."""
        ...

    def update(self, repository: Repository) -> None:
        """Replace the stored Repository with this one, matched on its id."""
        ...


@runtime_checkable
class RunRepository(Protocol):
    """Stored Runs. Every status write on a Run goes through `update` (AD-8)."""

    def add(self, run: Run) -> None:
        """Store a Run that does not exist yet."""
        ...

    def get(self, run_id: UUID) -> Run | None:
        """The Run with this id, or `None`."""
        ...

    def update(self, run: Run) -> None:
        """Replace the stored Run with this one, matched on its id."""
        ...

    def list_by_status(self, status: RunStatus) -> list[Run]:
        """Every Run in this status, newest first — what the queue view reads."""
        ...

    def list_by_repository_non_terminal(self, repository_id: UUID) -> list[Run]:
        """Every Run against this Repository that has not finished, newest first.

        Not finished means `status not in TERMINAL_RUN`: the set a second Run against the
        same Repository has to be checked against.
        """
        ...

    def list_by_after_run_id(self, run_id: UUID) -> list[Run]:
        """Every queued Run whose `after_run_id` equals `run_id` and `engine_ref` is empty.

        Returns only dependency-waiting runs: those that have not yet been enqueued
        (`engine_ref == {}`) so the caller does not double-enqueue an already-processing
        dependent.
        """
        ...

    # Declared last on purpose: the name `list` shadows the builtin for the rest of this
    # class body, so every `list[Run]` annotation above has to be read before it is bound.
    def list(self, *, project_id: UUID | None = None) -> list[Run]:
        """Every stored Run, newest first; scoped to one Project when asked.

        `project_id` is the Board's only filter (SPEC CAP-14). Newest first means
        `created_at` descending with `id` descending as the tiebreak — UUIDv7 sorts by
        creation, so two Runs created in the same millisecond still have one order.
        """
        ...


@runtime_checkable
class StepRunRepository(Protocol):
    """The planned rows of a Run, keyed by `seq` within it."""

    def add_many(self, steps: list[StepRun]) -> None:
        """Store a whole plan at once — a plan is written in one unit of work (AD-7)."""
        ...

    def get_by_seq(self, run_id: UUID, seq: int) -> StepRun | None:
        """The row of this Run at this `seq`, or `None`."""
        ...

    def list_for_run(self, run_id: UUID) -> list[StepRun]:
        """Every row of this Run, ordered by `seq`."""
        ...

    def update(self, step: StepRun) -> None:
        """Replace the stored row with this one, matched on its id."""
        ...

    def first_queued(self, run_id: UUID) -> StepRun | None:
        """The lowest-`seq` row of this Run in `queued`, or `None` — what the walker runs."""
        ...


@runtime_checkable
class AttemptRepository(Protocol):
    """The attempts at a row. `mark_started` and `mark_finished` are separate on purpose."""

    def add(self, attempt: Attempt) -> None:
        """Store an attempt that does not exist yet."""
        ...

    def get(self, attempt_id: UUID) -> Attempt | None:
        """The Attempt with this id, or `None` — direct lookup for the log endpoint."""
        ...

    def get_latest(self, step_run_id: UUID) -> Attempt | None:
        """The highest-`n` attempt at this row, or `None` if it has never run."""
        ...

    def latest_for_run(self, run_id: UUID) -> Attempt | None:
        """The most recently started Attempt for this Run across all rows, or `None`.

        Used by `signal_run` to check reply_available: whether the run's harness supports
        resume and whether the last attempt recorded a session_id (AD-10, story 3-3).
        """
        ...

    def list_for_row(self, step_run_id: UUID) -> list[Attempt]:
        """Every attempt at this row, ordered by `n`."""
        ...

    def mark_started(self, attempt: Attempt) -> None:
        """Write the start half: `started_at`, `start_sha`, `frozen_test_files`, `pgid`.

        Takes the whole updated entity rather than a keyword per column: AD-8 requires this
        half to commit in its own unit of work before the harness is awaited, and passing
        the columns separately would exceed ruff's `PLR0913` while making this repository
        the only one that is not entity-in, entity-out.
        """
        ...

    def mark_finished(self, attempt: Attempt) -> None:
        """Write the finish half: `ended_at`, `end_sha`, `exit_code`, `session_id`, the
        usage columns, `log_path`, `output_ref` and `status`. Entity in, for the same
        reason `mark_started` takes one."""
        ...

    def update(self, attempt: Attempt) -> None:
        """Replace the stored attempt with this one, matched on its id."""
        ...


@runtime_checkable
class GateRecordRepository(Protocol):
    """The gate record of a Run: append and read, and nothing else (AD-8)."""

    def add(self, record: GateRecord) -> None:
        """Append one record. Nothing updates or deletes one."""
        ...

    def list_for_run(self, run_id: UUID) -> list[GateRecord]:
        """Every record of this Run, oldest first, `id` breaking a tie on `at`."""
        ...
