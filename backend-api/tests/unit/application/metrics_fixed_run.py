"""One fixed Run on the shared fakes for the metric methods' tests (not a test module).

2 epics, 3 stories, 9 rows, 12 attempts; a timeline in seconds from `T0`, every attempt 600 s:

    A1  S0 plan        0-600     A7  S1 review     3800-4400
    A2  S0 implement   600-1200  A8  S2 plan       4400-5000
    A3  S0 implement 2 1300-1900 A9  S2 implement  5000-5600 (blocked, parks at 5650)
    A4  S1 plan       1900-2500  A10 S2 implement 2 7500-8100 (operator retry at 7450)
    A5  S1 implement  2500-3100  A11 S2 review     8100-8700
    A6  S1 implement 2 3200-3800 A12 S2 review 2   8700-9300 (consult, senior)

A3 is the redispatch re-run (record at 1250 on the shell row `S0.verify`), A6 the automatic
retry (record at 3150), A10 the operator retry. A12 has no harness money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from orchestrator.application.metrics.live import MetricsReadPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import (
    ActivityFact,
    AttemptFacts,
    FactSet,
    GapFact,
    GatewayRead,
    UsageFact,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.facts import FakeFactSetRepository, FakeGatewayReadRepository
from tests.unit.fakes.run_records import FakeRunRepositoryRecords
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID(int=1)
S0, S1, S2 = "epics[0].stories[0]", "epics[0].stories[1]", "epics[1].stories[0]"

#: (path, kind, role, status)
ROWS = [
    (f"{S0}.plan", "agent", "plan", "done"),
    (f"{S0}.implement", "agent", "implement", "done"),
    (f"{S0}.verify", "shell", "verify", "skipped"),
    (f"{S1}.plan", "agent", "plan", "done"),
    (f"{S1}.implement", "agent", "implement", "done"),
    (f"{S1}.review", "agent", "review", "done"),
    (f"{S2}.plan", "agent", "plan", "done"),
    (f"{S2}.implement", "agent", "implement", "done"),
    (f"{S2}.review", "agent", "review", "done"),
]

#: (row path, n, role, status, start s, gateway, harness or None, model)
ATTEMPTS = [
    (f"{S0}.plan", 1, "agent", "done", 0, "1", "1.1", "model-s"),
    (f"{S0}.implement", 1, "agent", "done", 600, "2", "2.1", "model-l"),
    (f"{S0}.implement", 2, "agent", "done", 1300, "3", "3.1", "model-l"),
    (f"{S1}.plan", 1, "agent", "done", 1900, "1", "1.1", "model-s"),
    (f"{S1}.implement", 1, "agent", "error", 2500, "2", "2.1", "model-l"),
    (f"{S1}.implement", 2, "agent", "done", 3200, "3", "3.1", "model-l"),
    (f"{S1}.review", 1, "agent", "done", 3800, "1", "1.1", "model-s"),
    (f"{S2}.plan", 1, "agent", "done", 4400, "1", "1.1", "model-s"),
    (f"{S2}.implement", 1, "agent", "blocked", 5000, "2", "2.1", "model-l"),
    (f"{S2}.implement", 2, "agent", "done", 7500, "3", "3.1", "model-l"),
    (f"{S2}.review", 1, "agent", "done", 8100, "1", "1.1", "model-s"),
    (f"{S2}.review", 2, "consult", "done", 8700, "2", None, "model-l"),
]

#: tokens per declared role: output, cache_read, input_uncached, cache_write_5m
TOKENS = {
    "plan": (100, 1000, 10, 100),
    "implement": (200, 3000, 20, 200),
    "review": (50, 500, 10, 90),
    "senior": (10, 100, 5, 5),
}

#: (offset s, event, actor, path)
RECORDS = [
    (0, "start", "machine", None),
    (1250, "redispatch", "machine", f"{S0}.verify"),
    (3150, "retry_auto", "machine", f"{S1}.implement"),
    (5650, "blocked", "machine", f"{S2}.implement"),
    (7450, "retry", "operator", f"{S2}.implement"),
    (9400, "done", "machine", None),
]


@dataclass
class FixedRun:
    ports: MetricsReadPorts
    run: Run
    attempts: dict[tuple[str, int], Attempt]
    records: FakeGateRecordRepository
    gateway_reads: FakeGatewayReadRepository
    fact_sets: FakeFactSetRepository


def _id(kind: int, n: int) -> UUID:
    return UUID(int=kind * 1000 + n)


def _facts(role: str, harness: str | None, model: str) -> AttemptFacts:
    output, read, fresh, write = TOKENS[role]
    usage = [
        UsageFact(source="harness", model=model, usage_class="output", tokens=output),
        UsageFact(source="harness", model=model, usage_class="cache_read", tokens=read),
        UsageFact(source="harness", model=model, usage_class="input_uncached", tokens=fresh),
        UsageFact(source="harness", model=model, usage_class="cache_write_5m", tokens=write),
    ]
    if harness is not None:
        usage.append(
            UsageFact(source="harness", model=model, usage_class="money", usd=Decimal(harness))
        )
    return AttemptFacts(
        usage=tuple(usage),
        activity=(
            ActivityFact(
                conversation="main",
                tool="Bash",
                calls=4,
                errors=1,
                files_read=2,
                files_edited=1,
                test_runs=1,
                messages=10,
            ),
        ),
        gaps=(
            GapFact(
                conversation="main",
                messages=10,
                first_at=T0,
                last_at=T0 + timedelta(seconds=600),
                gaps_s=(30, 4000),
            ),
        ),
    )


def build_fixed_run() -> FixedRun:
    run = Run(
        id=RUN_ID,
        project_id=UUID(int=2),
        repository_id=UUID(int=3),
        template_name="fixed",
        template_version=1,
        status="done",
        budget_usd=Decimal("50"),
        gateway_spend_usd=Decimal("22"),
        harness_spend_usd=Decimal("21.1"),
        gate_spend_usd=Decimal("23.1"),
        active_seconds=900,
        created_at=T0,
        started_at=T0,
        ended_at=T0 + timedelta(seconds=9400),
    )
    rows = {
        path: StepRun(
            id=_id(1, seq),
            run_id=RUN_ID,
            seq=seq,
            path=path,
            label=path.rsplit(".", 1)[-1],
            kind=kind,
            gate="deterministic",
            status=status,  # type: ignore[arg-type]
            frame=path.rsplit(".", 1)[0],
            story_id=f"story-{path.rsplit('.', 1)[0][-2]}",
            role=role,
        )
        for seq, (path, kind, role, status) in enumerate(ROWS, start=1)
    }
    runs = FakeRunRepository([run])
    steps = FakeStepRunRepository(list(rows.values()))
    attempts = FakeAttemptRepository()
    fact_sets = FakeFactSetRepository(attempts)
    reads = FakeGatewayReadRepository()
    stored: dict[tuple[str, int], Attempt] = {}
    for index, (path, n, role, status, start, gateway, harness, model) in enumerate(ATTEMPTS, 1):
        row = rows[path]
        attempt = Attempt(
            id=_id(2, index),
            run_id=RUN_ID,
            step_run_id=row.id,
            n=n,
            status=status,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            started_at=T0 + timedelta(seconds=start),
            ended_at=T0 + timedelta(seconds=start + 600),
            harness="claude",
            model=model,
        )
        attempts.add(attempt)
        stored[(path, n)] = attempt
        declared = "senior" if role == "consult" else row.role
        fact_sets.add(
            FactSet(
                id=_id(3, index),
                attempt_id=attempt.id,
                run_id=RUN_ID,
                extractor="claude",
                extractor_version=1,
                read_at=T0 + timedelta(seconds=start + 700),
                status="ok",
            ),
            _facts(declared, harness, model),
        )
        reads.add(
            GatewayRead(
                id=_id(4, index),
                attempt_id=attempt.id,
                run_id=RUN_ID,
                read_at=T0 + timedelta(seconds=start + 650),
                trigger="attempt_end",
                provisional=False,
                usd=Decimal(gateway),
            ),
            (UsageFact(source="gateway", model=model, usage_class="money", usd=Decimal(gateway)),),
        )
    records = FakeGateRecordRepository(
        [
            GateRecord(
                id=_id(5, index),
                run_id=RUN_ID,
                at=T0 + timedelta(seconds=at),
                path=path,
                event=event,  # type: ignore[arg-type]
                actor=actor,  # type: ignore[arg-type]
            )
            for index, (at, event, actor, path) in enumerate(RECORDS, 1)
        ]
    )
    ports = MetricsReadPorts(
        runs=runs,
        steps=steps,
        attempts=attempts,
        records=records,
        fact_sets=fact_sets,
        gateway_reads=reads,
        run_records=FakeRunRepositoryRecords(),
        clock=FakeClock(T0 + timedelta(seconds=9500)),
    )
    return FixedRun(ports, run, stored, records, reads, fact_sets)
