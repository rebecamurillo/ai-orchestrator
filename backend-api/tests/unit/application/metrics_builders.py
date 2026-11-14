"""Small hand-built `RunInputs` for the metric methods' branch tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, GatewayRead, UsageFact
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

T0 = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID(int=7)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def make_run(**fields: object) -> Run:
    base: dict[str, object] = {
        "id": RUN_ID,
        "project_id": uuid4(),
        "repository_id": uuid4(),
        "template_name": "t",
        "template_version": 1,
        "status": "done",
        "budget_usd": None,
        "created_at": T0,
        "started_at": T0,
        "ended_at": at(1000),
    }
    return Run(**{**base, **fields})  # type: ignore[arg-type]


def make_row(path: str = "build", seq: int = 1, kind: str = "agent", **fields: object) -> StepRun:
    base: dict[str, object] = {
        "id": uuid4(),
        "run_id": RUN_ID,
        "seq": seq,
        "path": path,
        "label": path.rsplit(".", 1)[-1],
        "kind": kind,
        "gate": "deterministic",
        "status": "done",
    }
    return StepRun(**{**base, **fields})  # type: ignore[arg-type]


def make_attempt(row: StepRun, n: int = 1, **fields: object) -> Attempt:
    base: dict[str, object] = {
        "id": uuid4(),
        "run_id": RUN_ID,
        "step_run_id": row.id,
        "n": n,
        "status": "done",
        "started_at": at(0),
        "ended_at": at(100),
        "model": "m",
    }
    return Attempt(**{**base, **fields})  # type: ignore[arg-type]


def make_read(
    attempt: Attempt, usd: str, *, provisional: bool = False, seconds: int = 0, **fields: object
) -> tuple[GatewayRead, tuple[UsageFact, ...]]:
    read = GatewayRead(
        id=uuid4(),
        attempt_id=attempt.id,
        run_id=RUN_ID,
        read_at=at(seconds),
        trigger="attempt_end",
        provisional=provisional,
        usd=Decimal(usd),
        **fields,  # type: ignore[arg-type]
    )
    return read, ()


def make_ai(
    row: StepRun,
    attempt: Attempt | None = None,
    *,
    facts: AttemptFacts | None = None,
    reads: tuple[tuple[GatewayRead, tuple[UsageFact, ...]], ...] = (),
    role: str = "build",
) -> AttemptInputs:
    attempt = attempt or make_attempt(row)
    fact_set = (
        FactSet(
            id=uuid4(),
            attempt_id=attempt.id,
            run_id=RUN_ID,
            extractor="x",
            extractor_version=1,
            read_at=at(0),
            status="ok",
        )
        if facts is not None
        else None
    )
    return AttemptInputs(attempt, row, role, reads, fact_set, facts)


def make_record(
    event: str, seconds: int, actor: str = "machine", path: str | None = None
) -> GateRecord:
    return GateRecord(
        id=uuid4(),
        run_id=RUN_ID,
        at=at(seconds),
        path=path,
        event=event,  # type: ignore[arg-type]
        actor=actor,  # type: ignore[arg-type]
    )


def make_inputs(
    rows: list[StepRun],
    attempts: list[AttemptInputs],
    records: list[GateRecord] | None = None,
    run: Run | None = None,
) -> RunInputs:
    return RunInputs(
        run=run or make_run(),
        rows=rows,
        attempts=attempts,
        records=records or [],
        now=at(2000),
    )
