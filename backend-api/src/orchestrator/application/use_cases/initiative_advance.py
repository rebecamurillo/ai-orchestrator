"""The durable advance after every terminal transition of an initiative Run (AD-8 amended,
AD-37 "Durability").

`record_advance` is the one thing a status writer does for the initiative: it inserts the
advance in the unit of work that ended the Run. `enqueue_advances` hands that advance to the
engine after the commit. `advance_initiative` is the workflow body: its reads first, under no
lock, then one unit of work that takes the initiative's row lock, re-checks what the reads
saw, and either consumes the advance, blocks it, or creates at most one Run with `consumed_at`
written in the Run's own commit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import structlog

from orchestrator.application.steps.gate_verdict import SPEC_GATE_ROLE
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    create_run,
)
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.initiatives import InitiativeAdvanceRepository, InitiativeRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import GateVerdict

log = structlog.get_logger(__name__)

ADVANCE_FAILED = "advance failed: {error}"
ADVANCE_LOGGED = "initiative advance failed"
MISSING = "no {what} {id}"


def _identity(text: str) -> str:
    return text


@dataclass(frozen=True)
class AdvancePorts:
    """What the advance workflow reaches the outside world through. Every new field defaults."""

    initiatives: InitiativeRepository
    advances: InitiativeAdvanceRepository
    runs: RunRepository
    create_run: CreateRunPorts
    uow: UnitOfWork
    clock: Clock
    redact: Callable[[str], str] = _identity
    steps: StepRunRepository | None = None
    attempts: AttemptRepository | None = None


@dataclass(frozen=True)
class NextRun:
    """Create this Run; `new_round` also moves the initiative to that round, in the same commit."""

    request: CreateRunRequest
    new_round: int | None = None


@dataclass(frozen=True)
class Blocked:
    """Nothing can be created yet; the reason is what the status function shows."""

    reason: str


Decision = NextRun | Blocked | None


def next_run(
    ports: AdvancePorts, initiative: Initiative, advance: InitiativeAdvance, from_run: Run
) -> Decision:
    """What follows a `done` Run of the initiative. Story 3 replaces this body."""
    return None


def gate_verdict_of(ports: AdvancePorts, run_id: UUID) -> GateVerdict | None:
    """The verdict stored on the Run's `spec-gate` row, from repositories alone."""
    if ports.steps is None or ports.attempts is None:
        return None
    gates = [row for row in ports.steps.list_for_run(run_id) if row.role == SPEC_GATE_ROLE]
    attempt = ports.attempts.get_latest(gates[-1].id) if gates else None
    if attempt is None or attempt.verdict_word is None:
        return None
    return GateVerdict(
        word=attempt.verdict_word,
        fields=dict(attempt.verdict_fields or {}),
        text=attempt.verdict_text or "",
    )


def _key(run: Run) -> tuple[int, int]:
    assert run.initiative_round is not None and run.initiative_position is not None
    return run.initiative_round, run.initiative_position


def record_advance(ports: WriterPorts, run: Run) -> None:
    """Insert the advance of a Run that has just ended, unless one is stored for its key."""
    if ports.advances is None or run.initiative_id is None or run.status not in TERMINAL_RUN:
        return
    round_, position = _key(run)
    stored = ports.advances.list_for_initiative(run.initiative_id)
    if any((a.round, a.position) == (round_, position) for a in stored):
        return
    ports.advances.add(
        InitiativeAdvance(
            id=new_id(),
            initiative_id=run.initiative_id,
            from_run_id=run.id,
            round=round_,
            position=position,
        )
    )


def enqueue_advances(engine: WorkflowEngine | None, ports: WriterPorts, run: Run) -> None:
    """After the commit: hand the Run's open advance to the engine."""
    if engine is None or ports.advances is None or run.initiative_id is None:
        return
    key = _key(run)
    for advance in ports.advances.list_for_initiative(run.initiative_id):
        if (advance.round, advance.position) == key and _open(advance):
            engine.enqueue_advance(advance.id)


def _open(advance: InitiativeAdvance) -> bool:
    return advance.consumed_at is None and advance.blocked_reason is None


@dataclass(frozen=True)
class _Plan:
    advance: InitiativeAdvance
    decision: Decision


def _required[T](value: T | None, what: str, id_: UUID) -> T:
    if value is None:
        raise LookupError(MISSING.format(what=what, id=id_))
    return value


def _superseded(initiative: Initiative, advance: InitiativeAdvance) -> bool:
    return initiative.cancelled_at is not None or advance.round < initiative.round


def _decide(ports: AdvancePorts, advance_id: UUID) -> _Plan | None:
    """Every read of the advance, with no lock and no unit of work. `None`: nothing to do."""
    advance = ports.advances.get(advance_id)
    if advance is None or advance.consumed_at is not None:
        return None
    initiative = _required(
        ports.initiatives.get(advance.initiative_id), "initiative", advance.initiative_id
    )
    if _superseded(initiative, advance):
        return _Plan(advance, None)
    from_run = _required(ports.runs.get(advance.from_run_id), "run", advance.from_run_id)
    if from_run.status != "done":
        return _Plan(advance, None)
    return _Plan(advance, next_run(ports, initiative, advance, from_run))


def _consume(ports: AdvancePorts, advance: InitiativeAdvance) -> None:
    ports.advances.update(advance.model_copy(update={"consumed_at": ports.clock.now()}))


def _create(
    ports: AdvancePorts, initiative: Initiative, advance: InitiativeAdvance, step: NextRun
) -> None:
    consumed = False

    def settle() -> None:
        nonlocal consumed
        consumed = True
        _consume(ports, advance)
        if step.new_round is not None:
            ports.initiatives.update(
                initiative.model_copy(
                    update={"round": step.new_round, "updated_at": ports.clock.now()}
                )
            )

    create_run(ports.create_run, step.request, before_commit=settle)
    if not consumed:
        _consume(ports, advance)
        ports.uow.commit()


def _apply(ports: AdvancePorts, plan: _Plan) -> None:
    """One unit of work under the initiative's row lock, re-checking what the reads saw."""
    with ports.uow:
        initiative = _required(
            ports.initiatives.get_for_update(plan.advance.initiative_id),
            "initiative",
            plan.advance.initiative_id,
        )
        advance = _required(ports.advances.get(plan.advance.id), "advance", plan.advance.id)
        if advance.consumed_at is not None:
            return
        decision = None if _superseded(initiative, advance) else plan.decision
        if isinstance(decision, NextRun):
            _create(ports, initiative, advance, decision)
            return
        if isinstance(decision, Blocked):
            ports.advances.update(advance.model_copy(update={"blocked_reason": decision.reason}))
        else:
            _consume(ports, advance)
        ports.uow.commit()


def _block(ports: AdvancePorts, advance_id: UUID, error: Exception) -> None:
    """Leave the advance unconsumed with the failure as its reason, in a unit of work of its own."""
    reason = ports.redact(ADVANCE_FAILED.format(error=error))
    with ports.uow:
        ports.uow.rollback()
        advance = ports.advances.get(advance_id)
        if advance is not None and advance.consumed_at is None:
            ports.advances.update(advance.model_copy(update={"blocked_reason": reason}))
        ports.uow.commit()


def advance_initiative(ports: AdvancePorts, advance_id: UUID) -> None:
    """Consume one advance: nothing to create, a block, or one Run. Never raises."""
    try:
        plan = _decide(ports, advance_id)
        if plan is not None:
            _apply(ports, plan)
    except Exception as error:
        log.exception(ADVANCE_LOGGED, advance_id=str(advance_id))
        _block(ports, advance_id, error)


def sweep_advances(ports: AdvancePorts, engine: WorkflowEngine, held: frozenset[UUID]) -> None:
    """At start-up: enqueue every open advance the engine does not hold."""
    with ports.uow:
        due = [a.id for a in ports.advances.list_unconsumed() if _open(a) and a.id not in held]
        ports.uow.commit()
    for advance_id in due:
        engine.enqueue_advance(advance_id)
