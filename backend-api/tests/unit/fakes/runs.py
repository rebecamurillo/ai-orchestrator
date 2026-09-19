"""In-memory fakes for the four Run repository ports (AD-18). Do not write another.

They hold entities, not rows, and they mirror what the tables in
`infrastructure/db/models/run.py` enforce, because a fake that accepted what an index
refuses would let 4.4's `create_run` and 4.6's walker pass their tests and fail on the first
real insert: a duplicate id, a second row at the same `(run_id, seq)` or `(run_id, path)`, a
second attempt at the same `(step_run_id, n)` — each is a `ValueError` here and a unique
violation there. Ordering is mirrored the same way: `list_for_run` by `seq`, `list_for_row`
by `n`, gate records by `(at, id)`, and every Run list newest first.

Every method appends `(name, argument)` to `self.calls` before it does anything else. The
brief asks for it because Epic 4's use cases are judged as much on *which* repository call
they made — one unit of work per transition (AD-8) — as on what they stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import TERMINAL_RUN, RunStatus


class FakeRunRepository:
    """Stored Runs in a dictionary, keyed by id."""

    def __init__(self, runs: list[Run] | None = None) -> None:
        self.runs: dict[UUID, Run] = {}
        self.calls: list[tuple[str, object]] = []
        for run in runs or []:
            self.add(run)

    def add(self, run: Run) -> None:
        self.calls.append(("add", run.id))
        if run.id in self.runs:
            raise ValueError(f"a run with id {run.id} is already stored")
        self.runs[run.id] = run

    def get(self, run_id: UUID) -> Run | None:
        self.calls.append(("get", run_id))
        return self.runs.get(run_id)

    def update(self, run: Run) -> None:
        self.calls.append(("update", run.id))
        if run.id not in self.runs:
            raise ValueError(f"no run with id {run.id} is stored")
        self.runs[run.id] = run

    def list(self, *, project_id: UUID | None = None) -> list[Run]:
        self.calls.append(("list", project_id))
        return _newest_first(
            run for run in self.runs.values() if project_id in (None, run.project_id)
        )

    def list_by_status(self, status: RunStatus) -> list[Run]:
        self.calls.append(("list_by_status", status))
        return _newest_first(run for run in self.runs.values() if run.status == status)

    def list_by_repository_non_terminal(self, repository_id: UUID) -> list[Run]:
        self.calls.append(("list_by_repository_non_terminal", repository_id))
        return _newest_first(
            run
            for run in self.runs.values()
            if run.repository_id == repository_id and run.status not in TERMINAL_RUN
        )

    def list_by_after_run_id(self, run_id: UUID) -> list[Run]:
        """Queued dependency-waiting runs: status='queued', after_run_id==run_id, engine_ref=={}."""
        self.calls.append(("list_by_after_run_id", run_id))
        return _newest_first(
            run
            for run in self.runs.values()
            if run.after_run_id == run_id and run.status == "queued" and not run.engine_ref
        )


class FakeStepRunRepository:
    """Stored planned rows in a dictionary, keyed by id."""

    def __init__(self, steps: list[StepRun] | None = None) -> None:
        self.steps: dict[UUID, StepRun] = {}
        self.calls: list[tuple[str, object]] = []
        if steps:
            self.add_many(steps)

    def add_many(self, steps: list[StepRun]) -> None:
        self.calls.append(("add_many", tuple(step.id for step in steps)))
        for step in steps:
            self._add(step)

    def _add(self, step: StepRun) -> None:
        if step.id in self.steps:
            raise ValueError(f"a step run with id {step.id} is already stored")
        for stored in self.steps.values():
            if stored.run_id != step.run_id:
                continue
            if stored.seq == step.seq:
                raise ValueError(f"run {step.run_id} already has a row at seq {step.seq}")
            if stored.path == step.path:
                raise ValueError(f"run {step.run_id} already has a row at {step.path!r}")
        self.steps[step.id] = step

    def get_by_seq(self, run_id: UUID, seq: int) -> StepRun | None:
        self.calls.append(("get_by_seq", (run_id, seq)))
        return next(
            (s for s in self.steps.values() if s.run_id == run_id and s.seq == seq),
            None,
        )

    def list_for_run(self, run_id: UUID) -> list[StepRun]:
        self.calls.append(("list_for_run", run_id))
        return sorted(
            (s for s in self.steps.values() if s.run_id == run_id),
            key=lambda step: step.seq,
        )

    def update(self, step: StepRun) -> None:
        self.calls.append(("update", step.id))
        if step.id not in self.steps:
            raise ValueError(f"no step run with id {step.id} is stored")
        self.steps[step.id] = step

    def first_queued(self, run_id: UUID) -> StepRun | None:
        self.calls.append(("first_queued", run_id))
        queued = [s for s in self.steps.values() if s.run_id == run_id and s.status == "queued"]
        return min(queued, key=lambda step: step.seq, default=None)


class FakeAttemptRepository:
    """Stored attempts in a dictionary, keyed by id."""

    def __init__(self, attempts: list[Attempt] | None = None) -> None:
        self.attempts: dict[UUID, Attempt] = {}
        self.calls: list[tuple[str, object]] = []
        for attempt in attempts or []:
            self.add(attempt)

    def add(self, attempt: Attempt) -> None:
        self.calls.append(("add", attempt.id))
        if attempt.id in self.attempts:
            raise ValueError(f"an attempt with id {attempt.id} is already stored")
        if any(
            stored.step_run_id == attempt.step_run_id and stored.n == attempt.n
            for stored in self.attempts.values()
        ):
            raise ValueError(f"row {attempt.step_run_id} already has attempt {attempt.n}")
        self.attempts[attempt.id] = attempt

    def get(self, attempt_id: UUID) -> Attempt | None:
        self.calls.append(("get", attempt_id))
        return self.attempts.get(attempt_id)

    def get_latest(self, step_run_id: UUID) -> Attempt | None:
        self.calls.append(("get_latest", step_run_id))
        stored = [a for a in self.attempts.values() if a.step_run_id == step_run_id]
        return max(stored, key=lambda attempt: attempt.n, default=None)

    def latest_for_run(self, run_id: UUID) -> Attempt | None:
        self.calls.append(("latest_for_run", run_id))
        stored = [a for a in self.attempts.values() if a.run_id == run_id]
        if not stored:
            return None
        return max(stored, key=lambda attempt: attempt.n)

    def list_for_row(self, step_run_id: UUID) -> list[Attempt]:
        self.calls.append(("list_for_row", step_run_id))
        return sorted(
            (a for a in self.attempts.values() if a.step_run_id == step_run_id),
            key=lambda attempt: attempt.n,
        )

    def mark_started(self, attempt: Attempt) -> None:
        self.calls.append(("mark_started", attempt.id))
        self._replace(attempt)

    def mark_finished(self, attempt: Attempt) -> None:
        self.calls.append(("mark_finished", attempt.id))
        self._replace(attempt)

    def update(self, attempt: Attempt) -> None:
        self.calls.append(("update", attempt.id))
        self._replace(attempt)

    def _replace(self, attempt: Attempt) -> None:
        if attempt.id not in self.attempts:
            raise ValueError(f"no attempt with id {attempt.id} is stored")
        self.attempts[attempt.id] = attempt


class FakeGateRecordRepository:
    """Stored gate records in a dictionary, keyed by id. Nothing here updates one."""

    def __init__(self, records: list[GateRecord] | None = None) -> None:
        self.records: dict[UUID, GateRecord] = {}
        self.calls: list[tuple[str, object]] = []
        for record in records or []:
            self.add(record)

    def add(self, record: GateRecord) -> None:
        self.calls.append(("add", record.id))
        if record.id in self.records:
            raise ValueError(f"a gate record with id {record.id} is already stored")
        self.records[record.id] = record

    def list_for_run(self, run_id: UUID) -> list[GateRecord]:
        self.calls.append(("list_for_run", run_id))
        return sorted(
            (r for r in self.records.values() if r.run_id == run_id),
            key=lambda record: (record.at, record.id),
        )


def _newest_first(runs: Iterable[Run]) -> list[Run]:
    """Runs ordered the way the Board reads them: `created_at` then `id`, both descending.

    UUIDv7 sorts by creation, so the id is the tiebreak for two Runs created in the same
    millisecond — the same order the adapter's `ORDER BY created_at DESC, id DESC` gives.
    """
    return sorted(runs, key=lambda run: (run.created_at, run.id), reverse=True)
