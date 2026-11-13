"""The metrics calculation job on the shared fakes (epic 2 story 5: AC1 job half, AC2, AC5,
AC6, AC8 wait half)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pytest

from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.use_cases.calculate_metrics import (
    CalculationPorts,
    begin_calculation,
    run_calculation,
)
from orchestrator.domain.entities.facts import AttemptFacts, FactSet
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.entities.metric_results import MetricCalculation
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.log_facts import LogFacts
from tests.unit.application.metrics_fixed_run import RUN_ID, T0, FixedRun, build_fixed_run
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository
from tests.unit.fakes.log_facts import ScriptedLogFacts
from tests.unit.fakes.metric_results import (
    FakeMetricCalculationRepository,
    FakeResultVersionRepository,
)

ATTEMPTS = 12
BOTH_READS = 24

PLAN_ROW = "epics[0].stories[0].plan"


@dataclass
class Job:
    fixed: FixedRun
    ports: CalculationPorts
    calculations: FakeMetricCalculationRepository
    versions: FakeResultVersionRepository
    gateway: FakeGateway
    holds: FakeInstanceHoldRepository
    existing: set[str]

    def queue(self, n: int = 1, state: str = "queued") -> UUID:
        calculation = MetricCalculation(
            id=new_id(),
            run_id=RUN_ID,
            target_n=n,
            state=state,  # type: ignore[arg-type]
            entry_point=("at_attempt_end",) if n == 1 else ("manual",),
            queued_at=self.ports.clock.now(),
        )
        self.calculations.add(calculation)
        return calculation.id

    def calculate(self, n: int = 1) -> UUID:
        calculation_id = self.queue(n)
        assert begin_calculation(self.ports, calculation_id) == "started"
        run_calculation(self.ports, calculation_id)
        return calculation_id


def a_job(extractors: dict[str, LogFacts] | None = None) -> Job:
    fixed = build_fixed_run()
    calculations = FakeMetricCalculationRepository()
    versions = FakeResultVersionRepository()
    gateway = FakeGateway()
    holds = FakeInstanceHoldRepository()
    existing: set[str] = set()
    read = fixed.ports
    ports = CalculationPorts(
        runs=read.runs,
        steps=read.steps,
        attempts=read.attempts,
        records=read.records,
        holds=holds,
        calculations=calculations,
        versions=versions,
        fact_sets=read.fact_sets,
        gateway_reads=read.gateway_reads,
        run_records=read.run_records,
        gateway=gateway,
        extractors=extractors or {},
        log_exists=lambda path: path in existing,
        clock=read.clock,
        uow=FakeUnitOfWork(),
    )
    return Job(fixed, ports, calculations, versions, gateway, holds, existing)


def state_of(job: Job, calculation_id: UUID) -> MetricCalculation:
    found = job.calculations.get(calculation_id)
    assert found is not None
    return found


def test_the_job_writes_one_version_holding_every_registered_method() -> None:
    job = a_job()

    calculation_id = job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    assert version.n == 1
    assert version.methods == tuple(sorted(REGISTRY))
    assert version.entry_point == ("at_attempt_end",)
    assert len(version.fact_set_ids) == ATTEMPTS
    assert list(version.fact_set_ids) == sorted(version.fact_set_ids)
    stored = job.versions.values(version.id)
    assert stored
    assert {v.origin.run_id for v in stored} == {RUN_ID}
    done = state_of(job, calculation_id)
    assert done.state == "done"
    assert done.output == f"v1: {len(stored)} values"
    assert done.started_at is not None
    assert done.ended_at is not None


def test_the_first_version_reads_the_gateway_for_run_end_and_later_ones_recalculate() -> None:
    job = a_job()

    job.calculate(1)
    job.calculate(2)

    triggers = [read.trigger for read, _ in job.fixed.gateway_reads.reads]
    assert triggers.count("run_end") == ATTEMPTS
    assert triggers.count("recalculation") == ATTEMPTS
    assert len(job.gateway.calls) == BOTH_READS


def test_a_cancelled_run_waits_for_its_open_attempt_then_includes_it() -> None:
    job = a_job()
    open_attempt = job.fixed.attempts[(PLAN_ROW, 1)]
    job.ports.attempts.attempts[open_attempt.id] = open_attempt.model_copy(
        update={"ended_at": None}
    )
    calculation_id = job.queue()

    assert begin_calculation(job.ports, calculation_id) == "waiting"
    assert state_of(job, calculation_id).state == "queued"
    assert job.versions.list_for_run(RUN_ID) == []

    job.ports.attempts.attempts[open_attempt.id] = open_attempt
    assert begin_calculation(job.ports, calculation_id) == "started"
    run_calculation(job.ports, calculation_id)

    [version] = job.versions.list_for_run(RUN_ID)
    keys = {v.scope_key for v in job.versions.values(version.id) if v.scope_type == "attempt"}
    assert f"{PLAN_ROW}#1" in keys


def test_a_non_harness_attempt_is_not_awaited() -> None:
    job = a_job()
    consult = job.fixed.attempts[("epics[1].stories[0].review", 2)]
    job.ports.attempts.attempts[consult.id] = consult.model_copy(
        update={"ended_at": None, "harness": None}
    )

    assert begin_calculation(job.ports, job.queue()) == "started"


def test_a_hold_keeps_a_queued_calculation_from_starting() -> None:
    job = a_job()
    now = job.ports.clock.now()
    job.holds.hold = InstanceHold(
        id=new_id(), held_at=now, expires_at=now + timedelta(hours=1), reason="upgrade"
    )
    calculation_id = job.queue()

    assert begin_calculation(job.ports, calculation_id) == "held"

    waiting = state_of(job, calculation_id)
    assert (waiting.state, waiting.started_at) == ("queued", None)
    assert "get_shared" in job.holds.calls


def test_an_expired_hold_does_not_hold() -> None:
    job = a_job()
    now = job.ports.clock.now()
    job.holds.hold = InstanceHold(
        id=new_id(),
        held_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        reason="x",
    )

    assert begin_calculation(job.ports, job.queue()) == "started"


def test_a_replay_or_an_unknown_calculation_is_skipped() -> None:
    job = a_job()
    done_id = job.calculate()

    assert begin_calculation(job.ports, done_id) == "skip"
    assert begin_calculation(job.ports, new_id()) == "skip"
    run_calculation(job.ports, done_id)
    run_calculation(job.ports, new_id())
    run_calculation(job.ports, job.queue(2))
    assert len(job.versions.list_for_run(RUN_ID)) == 1


def test_a_method_that_raises_fails_the_calculation_and_writes_nothing() -> None:
    job = a_job()

    def boom(_inputs: object) -> list[object]:
        raise RuntimeError("boom")

    REGISTRY["zz.boom@1"] = boom  # type: ignore[assignment]
    try:
        calculation_id = job.queue()
        assert begin_calculation(job.ports, calculation_id) == "started"
        run_calculation(job.ports, calculation_id)
    finally:
        del REGISTRY["zz.boom@1"]

    failed = state_of(job, calculation_id)
    assert failed.state == "failed"
    assert "RuntimeError: boom" in failed.output
    assert failed.ended_at is not None
    assert job.versions.versions == []


def test_a_failure_to_mark_a_vanished_calculation_is_not_an_error() -> None:
    job = a_job()
    calculation_id = job.queue()
    assert begin_calculation(job.ports, calculation_id) == "started"
    reads = iter([job.calculations.get(calculation_id)])
    job.calculations.get = lambda _id: next(reads, None)  # type: ignore[method-assign, assignment]
    job.ports.runs.runs.clear()  # type: ignore[attr-defined]

    run_calculation(job.ports, calculation_id)

    assert [c.state for c in job.calculations.rows] == ["running"]


def _fail_activity_facts(job: Job) -> UUID:
    attempt = job.fixed.attempts[(PLAN_ROW, 1)]
    sets = job.fixed.fact_sets.sets
    for index, stored in enumerate(sets):
        if stored.attempt_id == attempt.id:
            sets[index] = stored.model_copy(update={"status": "failed", "reason": "log swept"})
    return attempt.id


def _activity(job: Job, n: int) -> list:  # type: ignore[type-arg]
    version = job.versions.get(RUN_ID, n)
    assert version is not None
    return [
        v
        for v in job.versions.values(version.id)
        if v.metric_id.startswith("activity.") and v.scope_key == f"{PLAN_ROW}#1"
    ]


def test_a_figure_the_chosen_facts_lack_is_carried_from_the_earlier_version() -> None:
    job = a_job()
    job.calculate(1)
    before = {(v.metric_id, v.scope_key): v for v in _activity(job, 1)}
    assert before
    _fail_activity_facts(job)

    job.calculate(2)

    after = _activity(job, 2)
    carried = [v for v in after if v.carried_from == 1]
    assert carried
    for value in carried:
        assert value.value_num == before[(value.metric_id, value.scope_key)].value_num
        assert value.missing in (None, "partial")


def test_without_an_earlier_version_the_missing_figure_reads_not_recorded() -> None:
    job = a_job()
    _fail_activity_facts(job)

    job.calculate(1)

    words = [v for v in _activity(job, 1) if v.missing == "not recorded"]
    assert words
    assert all(v.carried_from is None and v.value_num is None for v in words)


def test_an_attempt_without_facts_gets_a_set_recorded_before_calculating() -> None:
    job = a_job()
    job.fixed.fact_sets.sets.clear()
    job.fixed.fact_sets.stored.clear()

    job.calculate()

    assert len(job.fixed.fact_sets.sets) == ATTEMPTS
    assert {s.status for s in job.fixed.fact_sets.sets} == {"failed"}


def attempt_with_log(job: Job, version_of_set: int = 1) -> UUID:
    attempt = job.fixed.attempts[(PLAN_ROW, 1)]
    job.ports.attempts.attempts[attempt.id] = attempt.model_copy(update={"log_path": "/logs/a1"})
    sets = job.fixed.fact_sets.sets
    for index, stored in enumerate(sets):
        if stored.attempt_id == attempt.id:
            sets[index] = stored.model_copy(update={"extractor": "claude"})
    return attempt.id


def sets_of(job: Job, attempt_id: UUID) -> list[FactSet]:
    return job.fixed.fact_sets.list_for_attempt(attempt_id)


def test_a_newer_extractor_reads_a_log_that_still_exists_again() -> None:
    extractor = ScriptedLogFacts(AttemptFacts(), name="claude", version=2)
    job = a_job({"claude": extractor})
    attempt_id = attempt_with_log(job)
    job.existing.add("/logs/a1")

    job.calculate()

    assert [s.extractor_version for s in sets_of(job, attempt_id)] == [1, 2]
    assert len(extractor.calls) == 1


def test_a_swept_log_is_not_extracted_again() -> None:
    extractor = ScriptedLogFacts(name="claude", version=2)
    job = a_job({"claude": extractor})
    attempt_id = attempt_with_log(job)

    job.calculate()

    assert len(sets_of(job, attempt_id)) == 1
    assert extractor.calls == []


def test_an_extractor_of_the_same_version_is_not_run_again() -> None:
    extractor = ScriptedLogFacts(name="claude", version=1)
    job = a_job({"claude": extractor})
    attempt_with_log(job)
    job.existing.add("/logs/a1")

    job.calculate()

    assert extractor.calls == []


def test_an_attempt_without_a_log_path_is_not_extracted_again() -> None:
    extractor = ScriptedLogFacts(name="claude", version=2)
    job = a_job({"claude": extractor})
    job.existing.add("/logs/a1")

    job.calculate()

    assert extractor.calls == []


def test_the_run_gateway_totals_are_recomputed_and_spend_is_left_alone() -> None:
    job = a_job()
    before = job.fixed.run

    job.calculate()

    after = job.ports.runs.get(RUN_ID)
    assert after is not None
    assert after.spend_usd == before.spend_usd
    assert after.gateway_spend_usd == before.gateway_spend_usd


@pytest.mark.parametrize("n", [1, 2])
def test_the_calculation_times_use_the_clock(n: int) -> None:
    job = a_job()

    calculation_id = job.calculate(n)

    assert state_of(job, calculation_id).ended_at == job.ports.clock.now()
    assert job.ports.clock.now() >= T0
