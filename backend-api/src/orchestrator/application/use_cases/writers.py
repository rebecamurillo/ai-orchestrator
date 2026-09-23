"""What the three status writers share: their ports, and the writes all three make.

AD-8 gives Run, Step, Attempt and gate-record state exactly two writers for execution
(`start_attempt`, `apply_step_result`) and one for the Operator (`signal_run`). They reach
the same four repositories through the same unit of work, append the same kind of record,
and re-queue a row by the same rule — so those things are written once, here, and the three
use cases hold only what is different about them.

Nothing in this module decides *whether* to write. Each function is the mechanics of one
write: `record` appends a line, `queue_row` moves a row to `queued` through the machine,
`finish_run` ends a Run. The rules that call them live in the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.trajectories import TrajectoryRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.statuses import (
    Actor,
    GateEvent,
    StepEvent,
    StepStatus,
    run_transition,
    step_transition,
)
from orchestrator.domain.values import Park

#: How a row in each status is put back on the queue. A row in any other status has no way
#: to `queued` in AD-8's diagram, so `step_transition` refuses it by name rather than this
#: table growing a case: `predecessor_done` is the only event a `planned` row accepts, and
#: asking for it from `done` or `running` is the bug the refusal reports.
QUEUE_EVENTS: dict[StepStatus, StepEvent] = {
    "planned": "predecessor_done",
    "error": "retry",
}

#: The statuses a row is finished in: the successor walk reads through them.
FINISHED: frozenset[StepStatus] = frozenset({"done", "skipped"})

#: What the gate record says when a Run starts and when it ends of its own accord.
RUN_STARTED = "run started"
RUN_DONE = "every planned step is done or skipped"

#: What the gate record says when the `recv` a parked Run waits in reaches its deadline.
#: AD-13 applies the expiry as Run `failed`, and `failed` is the event the alphabet has:
#: `expired` is not a `GateEvent` (`domain/statuses.py` says so in as many words), so the
#: sentence carries the thirty days and the event stays the lifecycle one.
RUN_EXPIRED = "parked 30 days"


@dataclass(frozen=True)
class WriterPorts:
    """The four repositories every status write goes through, plus the scope and the clock.

    `git` and `trajectories` (5.9) are the two `record_trajectory` needs beyond these four —
    both default `None` and degrade like `tracer`/`spend_writes`, so every `WriterPorts(...)`
    construction that predates this story keeps working unchanged.
    """

    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    records: GateRecordRepository
    uow: UnitOfWork
    clock: Clock
    git: Git | None = None
    trajectories: TrajectoryRepository | None = None
    #: Optional engine for two-phase dependent enqueue (story 5-4). `None` on every call
    #: site that predates this field — every frozen `WriterPorts(...)` construction keeps
    #: working unchanged. When set, `enqueue_dependents` uses it after a `done` transition.
    engine: WorkflowEngine | None = None


def require_run(ports: WriterPorts, run_id: UUID) -> Run:
    """The stored Run, or `NotFound` (404) — no writer invents one."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    return run


def require_row(ports: WriterPorts, run_id: UUID, seq: int) -> StepRun:
    """The Run's row at `seq`, or `NotFound` (404). `seq` is dense, so a gap is a bug."""
    row = ports.steps.get_by_seq(run_id, seq)
    if row is None:
        raise NotFound(f"no step {seq} on run {run_id}")
    return row


@dataclass(frozen=True)
class Entry:
    """One gate-record line before it has an id and a time — what a caller decides.

    A dataclass rather than six keyword arguments on `record`: ruff's `PLR0913` caps a
    signature at five, and the same reason `AttemptRepository.mark_started` takes an entity
    applies here — the columns belong together, so they travel together.
    """

    event: GateEvent
    actor: Actor
    #: The `step_run.path` the line is about, or `None` when it is about the Run.
    path: str | None = None
    text: str = ""
    attempt_n: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def record(ports: WriterPorts, run: Run, entry: Entry) -> GateRecord:
    """Append one gate-record line. Every Run transition appends exactly one (AD-8)."""
    line = GateRecord(
        id=new_id(),
        run_id=run.id,
        at=ports.clock.now(),
        path=entry.path,
        event=entry.event,
        actor=entry.actor,
        text=entry.text,
        attempt_n=entry.attempt_n,
        payload=dict(entry.payload),
    )
    ports.records.add(line)
    return line


def queue_row(ports: WriterPorts, row: StepRun) -> StepRun:
    """Put one row back on the queue through the machine, and store it."""
    event = QUEUE_EVENTS.get(row.status, "predecessor_done")
    updated = row.model_copy(update={"status": step_transition(row.status, event)})
    ports.steps.update(updated)
    return updated


def set_row(ports: WriterPorts, row: StepRun, **update: Any) -> StepRun:
    """Replace one row with the same row plus `update`. The only way a row is written."""
    updated = row.model_copy(update=update)
    ports.steps.update(updated)
    return updated


def set_run(ports: WriterPorts, run: Run, **update: Any) -> Run:
    """Replace the Run with the same Run plus `update`. The only way a Run is written."""
    updated = run.model_copy(update=update)
    ports.runs.update(updated)
    return updated


def clear_park(now: datetime | None = None) -> dict[str, Any]:
    """The three park fields, cleared — a Run outside `needs_you` carries none of them."""
    cleared: dict[str, Any] = {"park_kind": None, "park_path": None, "park_reason": None}
    if now is not None:
        cleared["ended_at"] = now
    return cleared


def park_run(
    ports: WriterPorts,
    run: Run,
    park: Park,
    attempt_n: int | None = None,
    payload: dict[str, Any] | None = None,
) -> Run:
    """Stop a Run for the Operator: the three park fields and one record, together.

    The only way `run.park_kind`, `run.park_path` and `run.park_reason` are written, so a
    parked Run always carries the three of them and the record that says the same thing.
    `path` is the park's own when it names one and the caller's row otherwise.

    `payload` is what the stop needs kept beyond its sentence — AD-17's list of the protected
    paths an attempt touched. It goes on the record, which is append-only, rather than on a
    Run column the next park would overwrite.
    """
    parked = set_run(
        ports,
        run,
        status=run_transition(run.status, "park"),
        park_kind=park.kind,
        park_path=park.path,
        park_reason=park.reason,
    )
    record(
        ports,
        parked,
        Entry(
            event=park.kind,
            actor="machine",
            path=park.path,
            text=park.reason,
            attempt_n=attempt_n,
            payload=payload or {},
        ),
    )
    return parked


def expire_run(ports: WriterPorts, run: Run) -> Run:
    """End a Run nobody answered: `needs_you → failed`, `ended_at`, one `failed` record.

    The walker calls this when its single `recv` reaches `HUMAN_WAIT_SECONDS` (AD-13). The
    park fields are cleared with the status for the reason `clear_park` exists: a Run
    outside `needs_you` carries none of them, and the sentence the Operator reads is on the
    record, which is append-only, rather than on a field the next write would overwrite.
    """
    now = ports.clock.now()
    expired = set_run(
        ports,
        run,
        status=run_transition(run.status, "expire"),
        **clear_park(now),
    )
    record(ports, expired, Entry(event="failed", actor="machine", text=RUN_EXPIRED))
    return expired


def finish_run(ports: WriterPorts, run: Run) -> Run:
    """End a Run that has nothing left to run: `running → done`, `ended_at`, one record."""
    now = ports.clock.now()
    finished = set_run(
        ports,
        run,
        status=run_transition(run.status, "finish"),
        **clear_park(now),
    )
    record(ports, finished, Entry(event="done", actor="machine", text=RUN_DONE))
    return finished


#: Reason text for a dependency park: the predecessor's terminal status (story 5-4).
DEPENDENCY_PARK_REASON = "run {run_id} ended {status}"

#: Reason text when a predecessor id no longer resolves to a stored Run (fan-in
#: `after_run_ids`, spine AD-12 amendment 2026-09-23). `after_run_ids` is an array with no
#: foreign key behind it, so a dangling edge is a state the resolver has to decide about,
#: and the conservative decision is to stop for the Operator: a park is reversible — AD-13
#: gives it Continue (start anyway) and Cancel — while skipping would leave the Run waiting
#: for something that can never arrive, invisible outside the queue's own row.
DEPENDENCY_MISSING_REASON = "run {run_id} is missing"

#: The predecessor statuses that stop a dependent from ever starting on its own (AD-12).
BLOCKING_RUN: frozenset[str] = frozenset({"failed", "cancelled"})


def resolve_dependent(
    ports: WriterPorts,
    engine: WorkflowEngine | None,
    dep: Run,
    *,
    own_uow: bool = True,
) -> None:
    """Apply AD-12's fan-in rule to one dependency-waiting Run.

    The rule is a read of the dependent's *whole* predecessor list, never of one Run:
    **all** of them `done` → the two-phase enqueue; **any** of them `failed | cancelled`
    (or missing) → a direct `dependency` park naming that one; anything else → still
    waiting, and nothing is written. The first blocking predecessor in declared order is
    the one the reason names, so the sentence the Operator reads is deterministic.

    `own_uow` says who owns the transaction the park is written in. `False` is the AD-8
    path — `park_dependents`, inside the predecessor's own terminal unit of work, where the
    spine requires the resolution to land with the status that caused it. `True` is the
    sweep and the post-commit enqueue path, which run with no transaction open.

    `after_run_ids` is never cleared here (AD-12, 2026-09-23): `list_dependents` filters on
    `engine_ref`, so the retained edges cost nothing and are what an initiative's DAG is
    rendered from.
    """
    if not dep.after_run_ids:
        return
    predecessors = [(pred_id, ports.runs.get(pred_id)) for pred_id in dep.after_run_ids]
    blocking = next(
        (pair for pair in predecessors if pair[1] is None or pair[1].status in BLOCKING_RUN),
        None,
    )
    if blocking is not None:
        _park_dependent(ports, dep, _dependency_reason(*blocking), own_uow=own_uow)
        return
    if all(stored is not None and stored.status == "done" for _id, stored in predecessors):
        _enqueue_dependent(ports, engine, dep)


def _dependency_reason(pred_id: UUID, predecessor: Run | None) -> str:
    """What the park says: the predecessor's terminal status, or that it is gone."""
    if predecessor is None:
        return DEPENDENCY_MISSING_REASON.format(run_id=pred_id)
    return DEPENDENCY_PARK_REASON.format(run_id=pred_id, status=predecessor.status)


def _park_dependent(ports: WriterPorts, dep: Run, reason: str, *, own_uow: bool) -> None:
    """Write the `dependency` park, in this function's own transaction or the caller's."""
    if not own_uow:
        _write_dependency_park(ports, dep, reason)
        return
    with ports.uow:
        _write_dependency_park(ports, dep, reason)
        ports.uow.commit()


def _write_dependency_park(ports: WriterPorts, dep: Run, reason: str) -> None:
    """`queued → needs_you` with the three park fields and one record, together.

    Direct rather than through `park_run`: the AD-8 `("queued", "park")` machine path does
    not exist, because every other park leaves `running`.
    """
    parked = dep.model_copy(
        update={
            "status": "needs_you",
            "park_kind": "dependency",
            "park_path": None,
            "park_reason": reason,
        }
    )
    ports.runs.update(parked)
    record(ports, parked, Entry(event="dependency", actor="machine", path=None, text=reason))


def _enqueue_dependent(ports: WriterPorts, engine: WorkflowEngine | None, dep: Run) -> None:
    """Two-phase: enqueue first, then commit the returned `engine_ref` in its own UoW.

    The order is AD-8's: the engine only ever sees a Run whose predecessor row is already
    durable. A `None` engine degrades to a no-op — every call site that predates story 5-4,
    and `park_dependents`, which can never reach this branch anyway.
    """
    if engine is None:
        return
    partition_key = (
        f"{dep.repository_id}:{dep.partition_branch or dep.inputs.get('base_branch', '')}"
    )
    engine_ref = engine.enqueue(dep.id, partition_key=partition_key)
    with ports.uow:
        refreshed = ports.runs.get(dep.id)
        if refreshed is not None:
            set_run(ports, refreshed, engine_ref=engine_ref)
        ports.uow.commit()


def park_dependents(ports: WriterPorts, run: Run) -> None:
    """Resolve every dependent of `run` in the same UoW as `run`'s terminal write.

    Called when `run` reaches `failed` or `cancelled`, from inside the unit of work that
    wrote that status (AD-8). `run` is by construction one of each dependent's
    predecessors and is blocking, so every resolution here is a park — which is why the
    engine is not passed: the enqueue branch is unreachable, and saying so structurally
    keeps this path from ever opening a second transaction inside the caller's.
    """
    for dep in ports.runs.list_dependents(run.id):
        resolve_dependent(ports, None, dep, own_uow=False)


def enqueue_dependents(ports: WriterPorts, engine: WorkflowEngine | None, run: Run) -> None:
    """Resolve every dependent of `run` after `run`'s `done` write is committed.

    Called with no transaction open, so each resolution owns its own. Idempotent: a
    dependent that was already enqueued carries an `engine_ref` and is invisible to
    `list_dependents`. Degrades to a no-op when `engine` is None (every call site that
    predates story 5-4).
    """
    if engine is None:
        return
    for dep in ports.runs.list_dependents(run.id):
        resolve_dependent(ports, engine, dep)
